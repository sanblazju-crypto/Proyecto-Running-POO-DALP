from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_

from app.database import get_db
from app.models import User, Post, Comment, post_likes, user_follows
from app.schemas import PostCreate, PostPublic, CommentCreate, CommentPublic
from app.auth.dependencies import get_current_user

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("", response_model=list[PostPublic])
async def get_feed(
    mode: str = Query("chronological", regex="^(chronological|relevance)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns posts from followed users + own posts.
    mode=chronological: newest first.
    mode=relevance: recent posts weighted by likes + comments (simple ranking).
    """
    following_ids_q = (
        select(user_follows.c.following_id)
        .where(user_follows.c.follower_id == current_user.id)
        .scalar_subquery()
    )

    q = (
        select(Post)
        .where(
            Post.is_public == True,
            Post.author_id.in_(following_ids_q)
            | (Post.author_id == current_user.id),
        )
    )

    if mode == "chronological":
        q = q.order_by(desc(Post.created_at))
    else:
        # Simple relevance: likes_count * 3 + comments_count * 2 - age_hours
        q = q.order_by(
            desc(Post.likes_count * 3 + Post.comments_count * 2),
            desc(Post.created_at),
        )

    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    posts = result.scalars().all()

    # Fetch which posts current user has liked
    liked_ids_result = await db.execute(
        select(post_likes.c.post_id).where(post_likes.c.user_id == current_user.id)
    )
    liked_ids = {str(r[0]) for r in liked_ids_result.fetchall()}

    output = []
    for post in posts:
        data = PostPublic.model_validate(post)
        data.is_liked = str(post.id) in liked_ids
        output.append(data)
    return output


@router.get("/explore", response_model=list[PostPublic])
async def explore_feed(
    discipline: str = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Public explore feed - posts from all users."""
    q = select(Post).where(Post.is_public == True)
    q = q.order_by(
        desc(Post.likes_count * 3 + Post.comments_count * 2),
        desc(Post.created_at),
    ).offset(skip).limit(limit)

    result = await db.execute(q)
    posts = result.scalars().all()

    liked_ids_result = await db.execute(
        select(post_likes.c.post_id).where(post_likes.c.user_id == current_user.id)
    )
    liked_ids = {str(r[0]) for r in liked_ids_result.fetchall()}

    return [
        {**PostPublic.model_validate(p).model_dump(), "is_liked": str(p.id) in liked_ids}
        for p in posts
    ]


@router.post("", response_model=PostPublic, status_code=201)
async def create_post(
    payload: PostCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = Post(
        author_id=current_user.id,
        content=payload.content,
        post_type=payload.post_type,
        activity_id=payload.activity_id,
        is_public=payload.is_public,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    data = PostPublic.model_validate(post)
    data.is_liked = False
    return data


@router.delete("/{post_id}", status_code=204)
async def delete_post(
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    if post.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Sin permisos")
    await db.delete(post)
    await db.commit()


@router.post("/{post_id}/like", status_code=204)
async def like_post(
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")

    existing = await db.scalar(
        select(func.count()).select_from(post_likes).where(
            post_likes.c.user_id == current_user.id,
            post_likes.c.post_id == post_id,
        )
    )
    if not existing:
        await db.execute(
            post_likes.insert().values(user_id=current_user.id, post_id=post_id)
        )
        post.likes_count += 1
        await db.commit()


@router.delete("/{post_id}/like", status_code=204)
async def unlike_post(
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")

    deleted = await db.execute(
        post_likes.delete().where(
            post_likes.c.user_id == current_user.id,
            post_likes.c.post_id == post_id,
        )
    )
    if deleted.rowcount > 0:
        post.likes_count = max(0, post.likes_count - 1)
        await db.commit()


@router.get("/{post_id}/comments", response_model=list[CommentPublic])
async def list_comments(
    post_id: UUID,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    result = await db.execute(
        select(Comment)
        .where(Comment.post_id == post_id, Comment.parent_id == None)
        .order_by(Comment.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/{post_id}/comments", response_model=CommentPublic, status_code=201)
async def add_comment(
    post_id: UUID,
    payload: CommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = await db.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")

    comment = Comment(
        post_id=post_id,
        author_id=current_user.id,
        content=payload.content,
        parent_id=payload.parent_id,
    )
    db.add(comment)
    post.comments_count += 1
    await db.commit()
    await db.refresh(comment)
    return comment


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    if comment.author_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Sin permisos")

    post = await db.get(Post, comment.post_id)
    if post:
        post.comments_count = max(0, post.comments_count - 1)

    await db.delete(comment)
    await db.commit()
