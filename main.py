from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel
from sqlmodel import Field, Relationship, Session, SQLModel, create_engine, select
from typing import List, Optional, Generator
import datetime
import enum
from contextlib import asynccontextmanager

DATABASE_URL = "sqlite:///./database.db"

engine = create_engine(DATABASE_URL, echo=True, connect_args={"check_same_thread": False})

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

class FeedbackType(str, enum.Enum):
    RECLAMACAO = "reclamacao"
    ELOGIO = "elogio"

class FeedbackBase(SQLModel):
    type: FeedbackType
    rating: int = Field(ge=1, le=5)
    comment: Optional[str] = None
    company_id: Optional[int] = Field(default=None, foreign_key="company.id")

class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    industry: Optional[str] = None

    feedbacks: List["Feedback"] = Relationship(back_populates="company")

class Feedback(FeedbackBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)

    company: Optional[Company] = Relationship(back_populates="feedbacks")

class FeedbackCreate(FeedbackBase):
    pass

class Reputation(BaseModel):
    company_id: int
    company_name: str
    average_rating: Optional[float] = None
    total_feedbacks: int
    feedback_with_rating_count: int

def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("INFO:     Iniciando aplicação e criando tabelas do banco de dados...")
    create_db_and_tables()
    with Session(engine) as session:
        statement = select(Company).limit(1)
        company_exists = session.exec(statement).first()
        if not company_exists:
            print("INFO:     Banco de dados vazio. Adicionando empresas iniciais...")
            company1 = Company(name="Empresa Alpha DB", industry="Tecnologia")
            company2 = Company(name="Consultoria Beta DB", industry="Consultoria")
            company3 = Company(name="Varejo Gamma DB", industry="Varejo")
            session.add(company1)
            session.add(company2)
            session.add(company3)
            session.commit()
            print("INFO:     Empresas iniciais adicionadas.")

    yield
    print("INFO:     Encerrando aplicação...")
app = FastAPI(
    title="Plataforma de Feedback de Funcionários API (SQLite)",
    description="MVP com persistência em SQLite usando SQLModel.",
    version="0.2.0",
    lifespan=lifespan
)


@app.get("/companies", response_model=List[Company], tags=["Companies"])
def get_companies(session: Session = Depends(get_session)):
    companies = session.exec(select(Company)).all()
    return companies

@app.get("/companies/{company_id}/feedbacks", response_model=List[Feedback], tags=["Feedbacks"])
def get_feedbacks_for_company(company_id: int, session: Session = Depends(get_session)):
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")

    statement = select(Feedback).where(Feedback.company_id == company_id)
    feedbacks = session.exec(statement).all()
    return feedbacks

@app.post("/feedbacks", response_model=Feedback, status_code=status.HTTP_201_CREATED, tags=["Feedbacks"])
def create_feedback(feedback_data: FeedbackCreate, session: Session = Depends(get_session)):
    company = session.get(Company, feedback_data.company_id)
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Empresa com ID {feedback_data.company_id} não encontrada."
        )

    db_feedback = Feedback.model_validate(feedback_data)

    session.add(db_feedback)
    session.commit()
    session.refresh(db_feedback)

    return db_feedback

@app.get("/companies/{company_id}/reputation", response_model=Reputation, tags=["Reputation"])
def get_company_reputation(company_id: int, session: Session = Depends(get_session)):

    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")

    statement = select(Feedback.rating).where(Feedback.company_id == company_id)
    ratings_result = session.exec(statement).all()

    total_feedbacks_statement = select(Feedback).where(Feedback.company_id == company_id)
    total_feedbacks = len(session.exec(total_feedbacks_statement).all())

    ratings = [r for r in ratings_result if r is not None]
    feedback_with_rating_count = len(ratings)

    average_rating: Optional[float] = None
    if feedback_with_rating_count > 0:
        average_rating = sum(ratings) / feedback_with_rating_count
        average_rating = round(average_rating, 2)

    return Reputation(
        company_id=company_id,
        company_name=company.name,
        average_rating=average_rating,
        total_feedbacks=total_feedbacks,
        feedback_with_rating_count=feedback_with_rating_count
    )

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Bem-vindo à API de Feedback de Funcionários! (Usando SQLite)"}