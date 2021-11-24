import secrets
from starlette import status

from fastapi import Depends
from fastapi.exceptions import HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext

from xyz_polyneme_ns.db import mongo_db
from xyz_polyneme_ns.models import Agent, get_agent_uri

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


security = HTTPBasic()


def get_current_agent(
    naan: int, credentials: HTTPBasicCredentials = Depends(security)
) -> Agent:
    mdb = mongo_db()
    agent_doc = mdb.agents.find_one({"id": get_agent_uri(naan, credentials.username)})
    agent = Agent(**agent_doc) if agent_doc else None
    if agent:
        correct_username = secrets.compare_digest(credentials.username, agent.username)
        pass_to_check = agent.hashed_password
    else:
        correct_username = secrets.compare_digest(
            credentials.username, "invalid-:!@#$%^&*():"
        )
        pass_to_check = "nope"

    try:
        verify_password(credentials.password, pass_to_check)
        correct_password = True
    except:
        correct_password = False

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return agent
