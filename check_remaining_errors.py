
import asyncio
import sys
import os
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure d:\AI is in path
sys.path.append(os.getcwd())

from api_gateway.models.database import AsyncSessionLocal, Error

async def check_remaining():
    async with AsyncSessionLocal() as session:
        # Get all unresolved errors
        result = await session.execute(
            select(Error).where(Error.resolved.is_(False))
        )
        errors = result.scalars().all()
        
        total_unresolved = len(errors)
        ready_for_review_count = len([e for e in errors if e.ready_for_review])
        needs_attention_count = total_unresolved - ready_for_review_count
        
        output = []
        output.append(f"Total Unresolved Errors: {total_unresolved}")
        output.append(f"Ready for Review: {ready_for_review_count}")
        output.append(f"Still Needing Fix (Not Ready): {needs_attention_count}")
        output.append("-" * 30)
        
        if needs_attention_count > 0:
            output.append("Items needing attention:")
            for e in errors:
                if not e.ready_for_review:
                    output.append(f"[{e.severity.value.upper()}] {e.service}: {e.message[:100]}...")
                    if e.context and 'file_path' in e.context:
                        output.append(f"  File: {e.context['file_path']}")
        
        with open('results.txt', 'w', encoding='utf-8') as f:
            f.write('\n'.join(output))
        print("Written to results.txt")

if __name__ == "__main__":
    asyncio.run(check_remaining())
