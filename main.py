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
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:3000", 
        "http://127.0.0.1:5500",
        "https://fud-anonymous.onrender.com",
        "https://fud-anonymous-b.onrender.com"
    ],
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

def safe_get(data: dict, key: str, default=None):
    """Safely get value from dictionary"""
    return data.get(key, default) if data else default

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
            liked_by = [like["user_id"] for like in likes_result.data] if likes_result.data else []
            
            # Get user reg_no safely
            user_reg_no = "Unknown"
            if post.get("user_id"):
                user_result = supabase.table("users").select("reg_no").eq("id", post["user_id"]).execute()
                if user_result.data and len(user_result.data) > 0:
                    user_reg_no = user_result.data[0].get("reg_no", "Unknown")
            
            posts.append(PostResponse(
                id=post["id"],
                user_id=post["user_id"],
                user_reg_no=user_reg_no,
                content=post.get("content", ""),
                type=post.get("type", "text"),
                likes=post.get("likes", 0),
                comments=post.get("comments", 0),
                liked_by=liked_by,
                created_at=post.get("created_at", datetime.utcnow().isoformat())
            ))
        
        return PostsResponse(posts=posts, total=total, page=page)
        
    except Exception as e:
        print(f"Error in get_posts: {e}")
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
            user_reg_no=current_user.get("reg_no", "Unknown"),
            content=post_data.content,
            type=post_data.type,
            likes=0,
            comments=0,
            liked_by=[],
            created_at=result.data[0]["created_at"]
        )
        
    except Exception as e:
        print(f"Error in create_post: {e}")
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
        print(f"Error in like_post: {e}")
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
        print(f"Error in unlike_post: {e}")
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
        for comment in result.data or []:
            # Get user reg_no safely
            user_reg_no = "Unknown"
            if comment.get("user_id"):
                user_result = supabase.table("users").select("reg_no").eq("id", comment["user_id"]).execute()
                if user_result.data and len(user_result.data) > 0:
                    user_reg_no = user_result.data[0].get("reg_no", "Unknown")
            
            comments.append(CommentResponse(
                id=comment["id"],
                post_id=comment["post_id"],
                user_id=comment["user_id"],
                user_reg_no=user_reg_no,
                content=comment.get("content", ""),
                created_at=comment.get("created_at", datetime.utcnow().isoformat())
            ))
        
        return CommentsResponse(comments=comments, total=len(comments))
        
    except Exception as e:
        print(f"Error in get_comments: {e}")
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
            user_reg_no=current_user.get("reg_no", "Unknown"),
            content=comment_data.content,
            created_at=result.data[0]["created_at"]
        )
        
    except Exception as e:
        print(f"Error in create_comment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== CHAT HELPER FUNCTIONS ==========
async def get_user_safe(user_id: str) -> dict:
    """Safely fetch user data with fallback"""
    try:
        if not user_id:
            return {"id": "", "reg_no": "Unknown", "full_name": "Unknown"}
        
        result = supabase.table("users").select("id, reg_no, full_name").eq("id", user_id).execute()
        if result.data and len(result.data) > 0:
            return result.data[0]
    except Exception as e:
        print(f"Error fetching user {user_id}: {e}")
    
    return {"id": user_id, "reg_no": "Unknown", "full_name": "Unknown"}

async def get_sender_reg_no(sender_id: str) -> str:
    """Safely get sender's registration number"""
    user = await get_user_safe(sender_id)
    return user.get("reg_no", "Anonymous")

async def ensure_private_chat_exists(chat_id: str, user_ids: list):
    """Ensure private chat exists and participants are added"""
    try:
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
            for uid in user_ids:
                participant_record = {
                    "chat_id": chat_id,
                    "user_id": uid,
                    "joined_at": datetime.utcnow().isoformat()
                }
                supabase.table("chat_participants").insert(participant_record).execute()
    except Exception as e:
        print(f"Error ensuring private chat exists: {e}")
    
    return chat_id

# ========== CHATS ENDPOINTS ==========
@app.get("/api/chats", response_model=ChatsResponse)
async def get_chats(current_user: dict = Depends(get_current_user)):
    """
    Get all chats where the current user is a participant
    """
    try:
        # Get all chats where user is participant
        participant_chats = supabase.table("chat_participants")\
            .select("chat_id")\
            .eq("user_id", current_user["id"])\
            .execute()
        
        chat_ids = [p["chat_id"] for p in participant_chats.data] if participant_chats.data else []
        
        if not chat_ids:
            return ChatsResponse(chats=[])
        
        # Get chat details - FIXED: desc=True → ascending=False
        chats_result = supabase.table("chats")\
            .select("*")\
            .in_("id", chat_ids)\
            .order("last_message_time", ascending=False)\
            .execute()
        
        chats = []
        for chat in chats_result.data or []:
            # Get participants for this chat
            participants_result = supabase.table("chat_participants")\
                .select("user_id")\
                .eq("chat_id", chat["id"])\
                .execute()
            
            participants = []
            for p in participants_result.data or []:
                user = await get_user_safe(p["user_id"])
                participants.append(ChatParticipant(
                    id=user["id"],
                    reg_no=user.get("reg_no", "Unknown"),
                    full_name=user.get("full_name", "Unknown")
                ))
            
            chats.append(ChatResponse(
                id=chat["id"],
                type=chat.get("type", "private"),
                last_message=chat.get("last_message"),
                last_message_time=chat.get("last_message_time"),
                participants=participants,
                created_at=chat.get("created_at", datetime.utcnow().isoformat())
            ))
        
        return ChatsResponse(chats=chats)
        
    except Exception as e:
        print(f"Error in get_chats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch chats: {str(e)}")

@app.get("/api/chats/{chat_id}/messages", response_model=MessagesResponse)
async def get_messages(
    chat_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Get messages for a specific chat (global or private)
    """
    try:
        # For private chats, verify user is a participant
        if chat_id != "global":
            participant = supabase.table("chat_participants")\
                .select("*")\
                .eq("chat_id", chat_id)\
                .eq("user_id", current_user["id"])\
                .execute()
            
            if not participant.data:
                raise HTTPException(
                    status_code=403, 
                    detail="You are not a participant in this chat"
                )
        
        # Get messages - FIXED: asc=True → ascending=True
        messages_result = supabase.table("messages")\
            .select("*")\
            .eq("chat_id", chat_id)\
            .order("created_at", ascending=True)\
            .limit(50)\
            .execute()
        
        messages = []
        for msg in messages_result.data or []:
            # Safely get sender's registration number
            sender_reg_no = await get_sender_reg_no(msg.get("sender_id"))
            
            messages.append(MessageResponse(
                id=msg.get("id", ""),
                chat_id=msg.get("chat_id", chat_id),
                sender_id=msg.get("sender_id", ""),
                sender_reg_no=sender_reg_no,
                content=msg.get("content", ""),
                created_at=msg.get("created_at", datetime.utcnow().isoformat())
            ))
        
        return MessagesResponse(messages=messages, chat_id=chat_id)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in get_messages for chat {chat_id}: {str(e)}")
        # Return empty messages instead of failing
        return MessagesResponse(messages=[], chat_id=chat_id)

@app.post("/api/chats/{chat_id}/messages", response_model=MessageResponse)
async def send_message(
    chat_id: str,
    message_data: MessageCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Send a message to a chat (creates private chat if needed)
    """
    try:
        # Handle private chat creation if needed
        if chat_id != "global" and "_" in chat_id:
            user_ids = chat_id.split("_")
            await ensure_private_chat_exists(chat_id, user_ids)
        
        # Create and send message
        message_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        message_record = {
            "id": message_id,
            "chat_id": chat_id,
            "sender_id": current_user["id"],
            "content": message_data.content,
            "created_at": now
        }
        
        result = supabase.table("messages").insert(message_record).execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to send message")
        
        # Update chat's last message
        supabase.table("chats").update({
            "last_message": message_data.content,
            "last_message_time": now
        }).eq("id", chat_id).execute()
        
        return MessageResponse(
            id=message_id,
            chat_id=chat_id,
            sender_id=current_user["id"],
            sender_reg_no=current_user.get("reg_no", "Anonymous"),
            content=message_data.content,
            created_at=now
        )
        
    except Exception as e:
        print(f"Error sending message to chat {chat_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

# ========== USER STATS ENDPOINTS ==========
@app.get("/api/users/stats", response_model=UserStatsResponse)
async def get_user_stats(current_user: dict = Depends(get_current_user)):
    """
    Get statistics for the current user
    """
    try:
        # Try to get from user_stats table first
        stats_result = supabase.table("user_stats")\
            .select("*")\
            .eq("user_id", current_user["id"])\
            .execute()
        
        if stats_result.data:
            stats = stats_result.data[0]
            return UserStatsResponse(
                posts_count=stats.get("posts_count", 0),
                comments_count=stats.get("comments_count", 0),
                likes_received=stats.get("likes_received", 0),
                chats_count=stats.get("chats_count", 0)
            )
        
        # Calculate stats manually if not in user_stats
        # Get posts count
        posts_count = supabase.table("posts")\
            .select("*", count="exact")\
            .eq("user_id", current_user["id"])\
            .execute()
        posts_count = posts_count.count if hasattr(posts_count, 'count') else 0
        
        # Get comments count
        comments_count = supabase.table("comments")\
            .select("*", count="exact")\
            .eq("user_id", current_user["id"])\
            .execute()
        comments_count = comments_count.count if hasattr(comments_count, 'count') else 0
        
        # Get likes received
        posts = supabase.table("posts")\
            .select("id")\
            .eq("user_id", current_user["id"])\
            .execute()
        
        likes_received = 0
        if posts.data:
            post_ids = [p["id"] for p in posts.data]
            likes_result = supabase.table("likes")\
                .select("*", count="exact")\
                .in_("post_id", post_ids)\
                .execute()
            likes_received = likes_result.count if hasattr(likes_result, 'count') else 0
        
        # Get chats count
        chats_count = supabase.table("chat_participants")\
            .select("*", count="exact")\
            .eq("user_id", current_user["id"])\
            .execute()
        chats_count = chats_count.count if hasattr(chats_count, 'count') else 0
        
        return UserStatsResponse(
            posts_count=posts_count,
            comments_count=comments_count,
            likes_received=likes_received,
            chats_count=chats_count
        )
        
    except Exception as e:
        print(f"Error getting user stats: {str(e)}")
        # Return zeros instead of failing
        return UserStatsResponse(
            posts_count=0,
            comments_count=0,
            likes_received=0,
            chats_count=0
        )

# ========== HEALTH CHECK ==========
@app.get("/api/health")
async def health_check():
    """
    Health check endpoint for monitoring
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "api": "up",
            "database": "unknown"
        }
    }
    
    try:
        if supabase:
            # Test database connection
            result = supabase.table("users").select("*", count="exact").limit(1).execute()
            health_status["services"]["database"] = "connected"
        else:
            health_status["services"]["database"] = "not_initialized"
            health_status["status"] = "degraded"
            
    except Exception as e:
        health_status["services"]["database"] = f"error: {str(e)}"
        health_status["status"] = "unhealthy"
    
    return health_status
