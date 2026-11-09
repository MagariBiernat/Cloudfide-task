from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Response

from ...api.dependencies import Repository
from .schemas import Todo, TodoCreate, TodosCleared, TodoUpdate

router = APIRouter(prefix="/api/todos", tags=["todos"])
TodoId = Annotated[int, Path(gt=0)]


@router.get("", response_model=list[Todo])
def list_todos(repo: Repository):
    return repo.list()


@router.post("", response_model=Todo, status_code=201)
def create_todo(payload: TodoCreate, repo: Repository):
    return repo.create(payload)


# Registered before the /{todo_id} routes: "completed" is not a valid TodoId.
@router.delete("/completed", response_model=TodosCleared)
def clear_completed(repo: Repository):
    return TodosCleared(deleted=repo.delete_completed())


@router.get("/{todo_id}", response_model=Todo)
def get_todo(todo_id: TodoId, repo: Repository):
    todo = repo.get(todo_id)
    if todo is None:
        raise HTTPException(404, "Task not found.")
    return todo


@router.patch("/{todo_id}", response_model=Todo)
def update_todo(todo_id: TodoId, payload: TodoUpdate, repo: Repository):
    todo = repo.update(todo_id, payload)
    if todo is None:
        raise HTTPException(404, "Task not found.")
    return todo


@router.delete("/{todo_id}", status_code=204)
def delete_todo(todo_id: TodoId, repo: Repository):
    if not repo.delete(todo_id):
        raise HTTPException(404, "Task not found.")
    return Response(status_code=204)
