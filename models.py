from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
import re
from datetime import datetime

# ========== AUTH MODELS ==========
class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    reg_no: str
    password: str = Field(..., min_length=8)

    @validator('reg_no')
    def validate_reg_no(cls, v):
        pattern = r'^[A-Z]{3}\/[A-Z]{3}\/\d{2}\/\d{4}$'
        if not re.match(pattern, v):
            raise ValueError('REG NO must be in format: XXX/XXX/XX/XXXX (all caps)')
        return v

class UserLogin(BaseModel):
    reg_no: str
    password: str

    @validator('reg_no')
    def validate_reg_no(cls, v):
        pattern = r'^[A-Z]{3}\/[A-Z]{3}\/\d{2}\/\d{4}$'
        if not re.match(pattern, v):
            raise ValueError('REG NO must be in format: XXX/XXX/XX/XXXX (all caps)')
        return v

class UserResponse(BaseModel):
    id: str
    full_name: str
    reg_no: str
    created_at: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

# ========== POST MODELS ==========
class PostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)
    type: str = "text"

class PostResponse(BaseModel):
    id: str
    user_id: str
    user_reg_no: str
    content: str
    type: str
    likes: int
    comments: int
    liked_by: List[str] = []
    created_at: str

class PostsResponse(BaseModel):
    posts: List[PostResponse]
    total: int
    page: int

# ========== COMMENT MODELS ==========
class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=200)

class CommentResponse(BaseModel):
    id: str
    post_id: str
    user_id: str
    user_reg_no: str
    content: str
    created_at: str

class CommentsResponse(BaseModel):
    comments: List[CommentResponse]
    total: int

# ========== CHAT MODELS ==========
class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=500)

class MessageResponse(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    sender_reg_no: str
    content: str
    created_at: str

class MessagesResponse(BaseModel):
    messages: List[MessageResponse]
    chat_id: str

class ChatParticipant(BaseModel):
    id: str
    reg_no: str
    full_name: str

class ChatResponse(BaseModel):
    id: str
    type: str
    last_message: Optional[str]
    last_message_time: Optional[str]
    participants: List[ChatParticipant]
    created_at: str

class ChatsResponse(BaseModel):
    chats: List[ChatResponse]

# ========== STATS MODELS ==========
class UserStatsResponse(BaseModel):
    posts_count: int
    comments_count: int
    likes_received: int
    chats_count: int
