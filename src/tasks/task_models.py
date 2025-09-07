from pydantic import BaseModel
from typing import Optional, List

class CommentTask(BaseModel):
    account_session: str
    account_number: str
    channel: str
    channel_id: int
    post_id: int
    comment_text: str
    delay: float = 0.0
    like_chance: int = 20
    reaction_types: List[str] = ["❤️", "👍", "🔥"]
    # Новые поля для автоопределения группы обсуждений
    discussion_group_id: Optional[int] = None  # ID группы обсуждений
    sender_chat_id: Optional[int] = None  # ID канала-отправителя

class CommentTaskMessage(BaseModel):
    data: List[CommentTask]

class LikeCommentTask(BaseModel):
    account_session: str
    account_number: str
    channel: str
    comment_id: int
    target_comment_account: str  # Аккаунт, чей комментарий лайкаем
    delay: float = 0.0
    reaction_types: List[str] = ["❤️", "👍", "🔥"]

class LikeCommentTaskMessage(BaseModel):
    data: List[LikeCommentTask]