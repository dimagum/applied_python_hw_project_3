import os

import string
import random
import threading
from datetime import datetime, timedelta
from typing import Optional, List

import nest_asyncio
import uvicorn
import redis
from pydantic import BaseModel, ConfigDict, field_validator
import jwt
from passlib.context import CryptContext

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship


SQLALCHEMY_DATABASE_URL = "sqlite:///./shortener.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
except Exception as e:
    print("Не удалось подключиться к Redis. Убедитесь, что сервер Redis запущен.")  # pragma: no cover

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    links = relationship("Link", back_populates="owner")

class Link(Base):
    __tablename__ = "links"
    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String, unique=True, index=True)
    original_url = Column(String, index=True)
    custom_alias = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    clicks = Column(Integer, default=0)
    last_clicked = Column(DateTime, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    owner = relationship("User", back_populates="links")

Base.metadata.create_all(bind=engine)


class UserCreate(BaseModel):
    username: str
    password: str

    @field_validator('password')
    def truncate_password(cls, v):
        return v[:72] if len(v) > 72 else v

class Token(BaseModel):
    access_token: str
    token_type: str

class LinkCreate(BaseModel):
    original_url: str
    custom_alias: Optional[str] = None
    expires_at: Optional[datetime] = None

class LinkResponse(BaseModel):
    short_code: str
    original_url: str
    expires_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

class LinkUpdate(BaseModel):
    original_url: str

class LinkStats(BaseModel):
    original_url: str
    created_at: datetime
    clicks: int
    last_clicked: Optional[datetime]


SECRET_KEY = "secret_token_key"
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=True)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=60)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username:
            return db.query(User).filter(User.username == username).first()
    except:
        return None
    return None


app = FastAPI(title="URL Shortener API")


@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "ok", "message": "My FastAPI service is running!"}



def generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

@app.post("/register", response_model=Token, tags=["Auth"])
def register(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed_password = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    return {"access_token": create_access_token(data={"sub": new_user.username}), "token_type": "bearer"}

@app.post("/token", response_model=Token, tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    return {"access_token": create_access_token(data={"sub": user.username}), "token_type": "bearer"}


@app.post("/links/shorten", response_model=LinkResponse, tags=["Links"])
def shorten_url(link_data: LinkCreate, user: Optional[User] = Depends(get_optional_user), db: Session = Depends(get_db)):
    short_code = link_data.custom_alias

    if short_code:
        if db.query(Link).filter((Link.short_code == short_code) | (Link.custom_alias == short_code)).first():
            raise HTTPException(status_code=400, detail="Alias already exists")
    else:
        while True:
            short_code = generate_short_code()
            if not db.query(Link).filter(Link.short_code == short_code).first():
                break

    new_link = Link(
        short_code=short_code,
        original_url=link_data.original_url,
        custom_alias=link_data.custom_alias,
        expires_at=link_data.expires_at,
        owner_id=user.id if user else None 
    )
    db.add(new_link)
    db.commit()
    db.refresh(new_link)
    return new_link


@app.get("/{short_code}", tags=["Links"])
def redirect_to_url(short_code: str, db: Session = Depends(get_db)):
    if redis_client is not None:
        cached_url = redis_client.get(short_code)
        if cached_url:
            return RedirectResponse(url=cached_url)
    

    link = db.query(Link).filter((Link.short_code == short_code) | (Link.custom_alias == short_code)).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
        
    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Link has expired")
        

    link.clicks += 1
    link.last_clicked = datetime.utcnow()
    db.commit()

    if 'redis_client' in globals() and redis_client is not None:
        redis_client.setex(short_code, 300, link.original_url)
    
    return RedirectResponse(url=link.original_url)


@app.get("/links/search", response_model=List[LinkResponse], tags=["Links"])
def search_by_url(original_url: str, db: Session = Depends(get_db)):
    return db.query(Link).filter(Link.original_url == original_url).all()

@app.get("/links/{short_code}/stats", response_model=LinkStats, tags=["Links"])
def get_stats(short_code: str, db: Session = Depends(get_db)):
    link = db.query(Link).filter((Link.short_code == short_code) | (Link.custom_alias == short_code)).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    return link

@app.put("/links/{short_code}", response_model=LinkResponse, tags=["Links"])
def update_link(short_code: str, link_data: LinkUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    link = db.query(Link).filter((Link.short_code == short_code) | (Link.custom_alias == short_code)).first()
    if not link or link.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized or link not found")
        
    link.original_url = link_data.original_url
    db.commit()
    db.refresh(link)
    

    if 'redis_client' in globals() and redis_client is not None:
        redis_client.delete(short_code)
    
    return link

@app.delete("/links/{short_code}", tags=["Links"])
def delete_link(short_code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    link = db.query(Link).filter((Link.short_code == short_code) | (Link.custom_alias == short_code)).first()
    if not link or link.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized or link not found")
        
    db.delete(link)
    db.commit()
    

    if 'redis_client' in globals() and redis_client is not None:
        redis_client.delete(short_code)
        
    return {"message": "Link deleted successfully"}


@app.delete("/admin/cleanup", tags=["Extra"])
def cleanup_unused_links(days: int = 30, db: Session = Depends(get_db)):
    """Удаление неиспользуемых ссылок (старше N дней)."""
    threshold = datetime.utcnow() - timedelta(days=days)
    unused_links = db.query(Link).filter(
        (Link.last_clicked < threshold) | 
        ((Link.last_clicked == None) & (Link.created_at < threshold))
    ).all()
    
    for link in unused_links:
        if 'redis_client' in globals():
            redis_client.delete(link.short_code)
        db.delete(link)
        
    db.commit()
    return {"deleted_count": len(unused_links)}


@app.get("/links/history/expired", tags=["Extra"])
def get_expired_links(db: Session = Depends(get_db)):
    """Отображение истории всех истекших ссылок."""
    now = datetime.utcnow()
    expired = db.query(Link).filter(Link.expires_at < now).all()
    return [{"short_code": l.short_code, "expires_at": l.expires_at} for l in expired]


nest_asyncio.apply()

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


# REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

# try:
#     redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)
#     redis_client.ping()
#     print(f"Redis connected to {REDIS_HOST}")
# except redis.exceptions.ConnectionError:
#     redis_client = None
#     print("Error")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")

try:
    redis_client = redis.Redis(
        host=REDIS_HOST, 
        port=6379, 
        db=0, 
        decode_responses=True,
        socket_connect_timeout=2
    )
    redis_client.ping()
    print(f"Успешное подключение к Redis на хосте: {REDIS_HOST}")
except Exception as e:
    print(f"Не удалось подключиться к Redis на хосте {REDIS_HOST}. Ошибка: {e}")
    redis_client = None

