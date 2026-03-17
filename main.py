from fastapi import FastAPI, HTTPException, status, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import timedelta
from typing import List, Optional
import uuid
from datetime import datetime

from database import supabase
from models import *
from auth import verify_password, get_password_hash, create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES

app = FastAPI(title="FUD Anonymous API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== HELPER FUNCTIONS ==========
def get_safe_email(reg_no: str) -> str:
    """Convert REG NO to email format for unique identification"""
    return reg_no.replace("/", "_").lower() + "@fud.edu.ng"

def mask_reg_no(reg_no: str) -> str:
    """Mask registration number for display"""
    if not reg_no:
        return "Anonymous"
    parts = reg_no.split('/')
    if len(parts) < 4:
        return reg_no
    return f"{parts[0]}/{parts[1]}/**/****"

# ========== CHECK SUPABASE CONNECTION ==========
@app.on_event("startup")
async def startup_event():
    """Check Supabase connection on startup"""
    if supabase is None:
        print("⚠️ WARNING: Supabase client not initialized. Check your environment variables.")
    else:
        try:
            # Test connection
            result = supabase.table("users").select("*", count="exact").limit(1).execute()
            print("✅ Supabase connection successful")
        except Exception as e:
            print(f"❌ Supabase connection failed: {e}")

# ========== ROOT ==========
@app.get("/")
async def root():
    return {
        "message": "FUD Anonymous API", 
        "status": "running",
        "supabase_connected": supabase is not None,
        "version": "1.0.0",
        "endpoints": [
            "/api/auth/signup",
            "/api/auth/login",
            "/api/auth/me",
            "/api/posts",
            "/api/posts/{post_id}/like",
            "/api/posts/{post_id}/unlike",
            "/api/posts/{post_id}/comments",
            "/api/chats",
            "/api/chats/{chat_id}/messages",
            "/api/users/stats",
            "/api/health"
        ]
    }

# ========== AUTH ENDPOINTS ==========
@app.post("/api/auth/signup", response_model=TokenResponse)
async def signup(user_data: UserCreate):
    try:
        # Check if user already exists
        existing = supabase.table("users").select("*").eq("reg_no", user_data.reg_no).execute()
        
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration number already exists"
            )
        
        # Create user
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(user_data.password)
        
        user_record = {
            "id": user_id,
            "full_name": user_data.full_name,
            "reg_no": user_data.reg_no,
            "email": get_safe_email(user_data.reg_no),
            "hashed_password": hashed_password,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("users").insert(user_record).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user"
            )
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_id}, expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user_id,
            full_name=user_data.full_name,
            reg_no=user_data.reg_no,
            created_at=result.data[0]["created_at"]
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(login_data: UserLogin):
    try:
        # Find user by reg_no
        result = supabase.table("users").select("*").eq("reg_no", login_data.reg_no).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid registration number or password"
            )
        
        user = result.data[0]
        
        # Verify password
        if not verify_password(login_data.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid registration number or password"
            )
        
        # Update online status
        supabase.table("users").update({"is_online": True, "last_active": "now()"}).eq("id", user["id"]).execute()
        
        # Create access token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user["id"]}, expires_delta=access_token_expires
        )
        
        user_response = UserResponse(
            id=user["id"],
            full_name=user["full_name"],
            reg_no=user["reg_no"],
            created_at=user["created_at"]
        )
        
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.get("/api/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        full_name=current_user["full_name"],
        reg_no=current_user["reg_no"],
        created_at=current_user["created_at"]
    )

# ========== POSTS ENDPOINTS ==========
@app.get("/api/posts", response_model=PostsResponse)
async def get_posts(
    page: int = Query(1, ge=1),
    sort: str = Query("latest", regex="^(latest|random)$"),
    current_user: dict = Depends(get_current_user)
):
    try:
        per_page = 10
        offset = (page - 1) * per_page
        
        # Get total count
        count_result = supabase.table("posts").select("*", count="exact").execute()
        total = count_result.count if hasattr(count_result, 'count') else 0
        
        # Get posts
        query = supabase.table("posts").select("*").order("created_at", desc=True)
        
        if sort == "random":
            # For random, we'll get more and shuffle in the frontend
            posts_result = query.limit(50).execute()
        else:
            posts_result = query.range(offset, offset + per_page - 1).execute()
        
        posts = []
        for post in posts_result.data:
            # Get liked_by for this post
            likes_result = supabase.table("likes").select("user_id").eq("post_id", post["id"]).execute()
            liked_by = [like["user_id"] for like in likes_result.data]
            
            # Get user reg_no
            user_result = supabase.table("users").select("reg_no").eq("id", post["user_id"]).execute()
            user_reg_no = user_result.data[0]["reg_no"] if user_result.data else "Unknown"
            
            posts.append(PostResponse(
                id=post["id"],
                user_id=post["user_id"],
                user_reg_no=user_reg_no,
                content=post["content"],
                type=post["type"],
                likes=post["likes"],
                comments=post["comments"],
                liked_by=liked_by,
                created_at=post["created_at"]
            ))
        
        return PostsResponse(posts=posts, total=total, page=page)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/posts", response_model=PostResponse)
async def create_post(
    post_data: PostCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        post_id = str(uuid.uuid4())
        
        post_record = {
            "id": post_id,
            "user_id": current_user["id"],
            "content": post_data.content,
            "type": post_data.type,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("posts").insert(post_record).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create post")
        
        return PostResponse(
            id=post_id,
            user_id=current_user["id"],
            user_reg_no=current_user["reg_no"],
            content=post_data.content,
            type=post_data.type,
            likes=0,
            comments=0,
            liked_by=[],
            created_at=result.data[0]["created_at"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/posts/{post_id}/like")
async def like_post(
    post_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        # Check if already liked
        existing = supabase.table("likes").select("*").eq("post_id", post_id).eq("user_id", current_user["id"]).execute()
        
        if existing.data:
            raise HTTPException(status_code=400, detail="Already liked this post")
        
        # Add like
        like_record = {
            "id": str(uuid.uuid4()),
            "post_id": post_id,
            "user_id": current_user["id"]
        }
        
        supabase.table("likes").insert(like_record).execute()
        
        return {"message": "Post liked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/posts/{post_id}/unlike")
async def unlike_post(
    post_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        result = supabase.table("likes").delete().eq("post_id", post_id).eq("user_id", current_user["id"]).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Like not found")
        
        return {"message": "Post unliked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== COMMENTS ENDPOINTS ==========
@app.get("/api/posts/{post_id}/comments", response_model=CommentsResponse)
async def get_comments(
    post_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        result = supabase.table("comments").select("*").eq("post_id", post_id).order("created_at", desc=True).limit(20).execute()
        
        comments = []
        for comment in result.data:
            # Get user reg_no
            user_result = supabase.table("users").select("reg_no").eq("id", comment["user_id"]).execute()
            user_reg_no = user_result.data[0]["reg_no"] if user_result.data else "Unknown"
            
            comments.append(CommentResponse(
                id=comment["id"],
                post_id=comment["post_id"],
                user_id=comment["user_id"],
                user_reg_no=user_reg_no,
                content=comment["content"],
                created_at=comment["created_at"]
            ))
        
        return CommentsResponse(comments=comments, total=len(comments))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/posts/{post_id}/comments", response_model=CommentResponse)
async def create_comment(
    post_id: str,
    comment_data: CommentCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        comment_id = str(uuid.uuid4())
        
        comment_record = {
            "id": comment_id,
            "post_id": post_id,
            "user_id": current_user["id"],
            "content": comment_data.content,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("comments").insert(comment_record).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create comment")
        
        return CommentResponse(
            id=comment_id,
            post_id=post_id,
            user_id=current_user["id"],
            user_reg_no=current_user["reg_no"],
            content=comment_data.content,
            created_at=result.data[0]["created_at"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== CHATS ENDPOINTS ==========
@app.get("/api/chats", response_model=ChatsResponse)
async def get_chats(current_user: dict = Depends(get_current_user)):
    try:
        # Get all chats where user is participant
        participant_chats = supabase.table("chat_participants").select("chat_id").eq("user_id", current_user["id"]).execute()
        chat_ids = [p["chat_id"] for p in participant_chats.data]
        
        if not chat_ids:
            return ChatsResponse(chats=[])
        
        # Get chat details
        chats_result = supabase.table("chats").select("*").in_("id", chat_ids).order("last_message_time", desc=True).execute()
        
        chats = []
        for chat in chats_result.data:
            # Get participants
            participants_result = supabase.table("chat_participants").select("user_id").eq("chat_id", chat["id"]).execute()
            
            participants = []
            for p in participants_result.data:
                user_result = supabase.table("users").select("id, reg_no, full_name").eq("id", p["user_id"]).execute()
                if user_result.data:
                    user = user_result.data[0]
                    participants.append(ChatParticipant(
                        id=user["id"],
                        reg_no=user["reg_no"],
                        full_name=user["full_name"]
                    ))
            
            chats.append(ChatResponse(
                id=chat["id"],
                type=chat["type"],
                last_message=chat.get("last_message"),
                last_message_time=chat.get("last_message_time"),
                participants=participants,
                created_at=chat["created_at"]
            ))
        
        return ChatsResponse(chats=chats)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chats/{chat_id}/messages", response_model=MessagesResponse)
async def get_messages(
    chat_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        # Check if user is participant (except for global chat)
        if chat_id != "global":
            participant = supabase.table("chat_participants").select("*").eq("chat_id", chat_id).eq("user_id", current_user["id"]).execute()
            if not participant.data:
                raise HTTPException(status_code=403, detail="Not a participant in this chat")
        
        # Get messages
        messages_result = supabase.table("messages").select("*").eq("chat_id", chat_id).order("created_at", asc=True).limit(50).execute()
        
        messages = []
        for msg in messages_result.data:
            # Get sender reg_no
            user_result = supabase.table("users").select("reg_no").eq("id", msg["sender_id"]).execute()
            sender_reg_no = user_result.data[0]["reg_no"] if user_result.data else "Unknown"
            
            messages.append(MessageResponse(
                id=msg["id"],
                chat_id=msg["chat_id"],
                sender_id=msg["sender_id"],
                sender_reg_no=sender_reg_no,
                content=msg["content"],
                created_at=msg["created_at"]
            ))
        
        return MessagesResponse(messages=messages, chat_id=chat_id)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chats/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    chat_id: str,
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        # Handle private chat creation
        if chat_id != "global" and "_" in chat_id:
            # Check if chat exists
            chat_result = supabase.table("chats").select("*").eq("id", chat_id).execute()
            
            if not chat_result.data:
                # Create new private chat
                chat_record = {
                    "id": chat_id,
                    "type": "private",
                    "created_at": datetime.utcnow().isoformat()
                }
                supabase.table("chats").insert(chat_record).execute()
                
                # Add participants
                user_ids = chat_id.split("_")
                for uid in user_ids:
                    participant_record = {
                        "chat_id": chat_id,
                        "user_id": uid,
                        "joined_at": datetime.utcnow().isoformat()
                    }
                    supabase.table("chat_participants").insert(participant_record).execute()
        
        # Send message
        message_id = str(uuid.uuid4())
        message_record = {
            "id": message_id,
            "chat_id": chat_id,
            "sender_id": current_user["id"],
            "content": message_data.content,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("messages").insert(message_record).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to send message")
        
        # Update chat last message
        supabase.table("chats").update({
            "last_message": message_data.content,
            "last_message_time": datetime.utcnow().isoformat()
        }).eq("id", chat_id).execute()
        
        return MessageResponse(
            id=message_id,
            chat_id=chat_id,
            sender_id=current_user["id"],
            sender_reg_no=current_user["reg_no"],
            content=message_data.content,
            created_at=result.data[0]["created_at"]
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== USER STATS ENDPOINTS ==========
@app.get("/api/users/stats", response_model=UserStatsResponse)
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    try:
        # Get stats from user_stats table or calculate
        stats_result = supabase.table("user_stats").select("*").eq("user_id", current_user["id"]).execute()
        
        if stats_result.data:
            stats = stats_result.data[0]
            return UserStatsResponse(
                posts_count=stats["posts_count"],
                comments_count=stats["comments_count"],
                likes_received=stats["likes_received"],
                chats_count=stats["chats_count"]
            )
        
        # Calculate if not exists
        posts_count = supabase.table("posts").select("*", count="exact").eq("user_id", current_user["id"]).execute().count
        comments_count = supabase.table("comments").select("*", count="exact").eq("user_id", current_user["id"]).execute().count
        
        # Get likes received
        posts = supabase.table("posts").select("id").eq("user_id", current_user["id"]).execute()
        post_ids = [p["id"] for p in posts.data]
        likes_received = 0
        if post_ids:
            likes_result = supabase.table("likes").select("*", count="exact").in_("post_id", post_ids).execute()
            likes_received = likes_result.count if hasattr(likes_result, 'count') else 0
        
        chats_count = supabase.table("chat_participants").select("*", count="exact").eq("user_id", current_user["id"]).execute().count
        
        return UserStatsResponse(
            posts_count=posts_count or 0,
            comments_count=comments_count or 0,
            likes_received=likes_received or 0,
            chats_count=chats_count or 0
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== HEALTH CHECK ==========
@app.get("/api/health")
async def health_check():
    try:
        # Test database connection
        if supabase:
            result = supabase.table("users").select("*", count="exact").limit(1).execute()
            return {
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "degraded",
                "database": "disconnected",
                "error": "Supabase client not initialized",
                "timestamp": datetime.utcnow().isoformat()
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
