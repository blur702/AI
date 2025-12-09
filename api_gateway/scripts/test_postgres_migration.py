#!/usr/bin/env python3
"""
Test script to verify PostgreSQL migration and connectivity.

Usage:
    python -m api_gateway.scripts.test_postgres_migration
"""

import asyncio
import sys
import uuid
from datetime import datetime

from sqlalchemy import text

from api_gateway.config import settings


async def test_connection():
    """Test basic PostgreSQL connectivity."""
    print("Testing PostgreSQL connection...")
    print(f"  Host: {settings.POSTGRES_HOST}")
    print(f"  Port: {settings.POSTGRES_PORT}")
    print(f"  Database: {settings.POSTGRES_DB}")
    print(f"  User: {settings.POSTGRES_USER}")

    import asyncpg

    try:
        conn = await asyncpg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
        )
        version = await conn.fetchval("SELECT version()")
        print(f"  PostgreSQL version: {version[:50]}...")
        await conn.close()
        print("  Connection test: PASSED")
        return True
    except Exception as e:
        print(f"  Connection test: FAILED - {e}")
        return False


async def test_sqlalchemy_engine():
    """Test SQLAlchemy async engine."""
    print("\nTesting SQLAlchemy async engine...")

    from api_gateway.models.database import engine

    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            print("  Engine connection: PASSED")
        return True
    except Exception as e:
        print(f"  Engine connection: FAILED - {e}")
        return False


async def test_table_creation():
    """Test that tables exist and are accessible."""
    print("\nTesting table accessibility...")

    from api_gateway.models.database import AsyncSessionLocal, init_db

    try:
        await init_db()
        print("  Table initialization: PASSED")

        async with AsyncSessionLocal() as session:
            # Test jobs table
            result = await session.execute(text("SELECT COUNT(*) FROM jobs"))
            job_count = result.scalar()
            print(f"  Jobs table accessible: PASSED ({job_count} records)")

            # Test api_keys table
            result = await session.execute(text("SELECT COUNT(*) FROM api_keys"))
            key_count = result.scalar()
            print(f"  API Keys table accessible: PASSED ({key_count} records)")

            # Test todos table
            result = await session.execute(text("SELECT COUNT(*) FROM todos"))
            todo_count = result.scalar()
            print(f"  Todos table accessible: PASSED ({todo_count} records)")

            # Test errors table
            result = await session.execute(text("SELECT COUNT(*) FROM errors"))
            error_count = result.scalar()
            print(f"  Errors table accessible: PASSED ({error_count} records)")

        return True
    except Exception as e:
        print(f"  Table test: FAILED - {e}")
        return False


async def test_crud_operations():
    """Test basic CRUD operations."""
    print("\nTesting CRUD operations...")

    from sqlalchemy import select, delete

    from api_gateway.models.database import (
        AsyncSessionLocal,
        Job,
        JobStatus,
        Todo,
        TodoStatus,
        Error,
        ErrorSeverity,
    )

    test_id = str(uuid.uuid4())

    try:
        async with AsyncSessionLocal() as session:
            # Test Job CRUD
            job = Job(
                id=test_id,
                service="test_service",
                status=JobStatus.pending,
                request_data={"test": "data"},
            )
            session.add(job)
            await session.commit()
            print("  Job CREATE: PASSED")

            result = await session.execute(select(Job).where(Job.id == test_id))
            fetched_job = result.scalar_one()
            assert fetched_job.service == "test_service"
            print("  Job READ: PASSED")

            fetched_job.status = JobStatus.completed
            await session.commit()
            print("  Job UPDATE: PASSED")

            await session.execute(delete(Job).where(Job.id == test_id))
            await session.commit()
            print("  Job DELETE: PASSED")

            # Test Todo CRUD
            todo_id = str(uuid.uuid4())
            todo = Todo(
                id=todo_id,
                title="Test Todo",
                description="Test description",
                status=TodoStatus.pending,
                priority=1,
            )
            session.add(todo)
            await session.commit()
            print("  Todo CREATE: PASSED")

            await session.execute(delete(Todo).where(Todo.id == todo_id))
            await session.commit()
            print("  Todo DELETE: PASSED")

            # Test Error CRUD
            error_id = str(uuid.uuid4())
            error_record = Error(
                id=error_id,
                service="test_service",
                severity=ErrorSeverity.error,
                message="Test error message",
                context={"key": "value"},
            )
            session.add(error_record)
            await session.commit()
            print("  Error CREATE: PASSED")

            await session.execute(delete(Error).where(Error.id == error_id))
            await session.commit()
            print("  Error DELETE: PASSED")

        return True
    except Exception as e:
        print(f"  CRUD test: FAILED - {e}")
        return False


async def run_all_tests():
    """Run all migration tests."""
    print("=" * 60)
    print("PostgreSQL Migration Test Suite")
    print("=" * 60)

    results = []

    results.append(await test_connection())
    results.append(await test_sqlalchemy_engine())
    results.append(await test_table_creation())
    results.append(await test_crud_operations())

    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)

    if all(results):
        print(f"ALL TESTS PASSED ({passed}/{total})")
        print("=" * 60)
        return True
    else:
        print(f"SOME TESTS FAILED ({passed}/{total} passed)")
        print("=" * 60)
        return False


def main():
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
