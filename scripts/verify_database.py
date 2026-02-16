"""
Database Verification Script
Checks that all collections are properly populated after code generation.

Usage:
    cd backend
    python scripts/verify_database.py
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings
import structlog

logger = structlog.get_logger(__name__)

async def verify_database():
    """Verify MongoDB collections after code generation"""
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_database]
    
    print("\n=== DATABASE VERIFICATION ===\n")
    
    # 1. Check Projects Collection
    projects_count = await db.projects.count_documents({})
    print(f"✓ Projects: {projects_count} documents")
    
    if projects_count > 0:
        latest_project = await db.projects.find_one(sort=[("created_at", -1)])
        print(f"  Latest Project ID: {latest_project['project_id']}")
        print(f"  Name: {latest_project['name']}")
        print(f"  User ID: {latest_project['user_id']}")
        project_id = latest_project['project_id']
    else:
        print("  ⚠ No projects found!")
        return
    
    # 2. Check SCP Versions
    scp_count = await db.scp_versions.count_documents({"project_id": project_id})
    print(f"\n✓ SCP Versions for {project_id}: {scp_count} documents")
    
    if scp_count > 0:
        latest_scp = await db.scp_versions.find_one({"project_id": project_id})
        print(f"  Version: {latest_scp.get('version', 'N/A')}")
        print(f"  Complexity: {latest_scp.get('complexity', 'N/A')}")
        print(f"  Has SCP Document: {'scp' in latest_scp}")
    else:
        print("  ⚠ No SCP versions found!")
    
    # 3. Check Files Collection
    files_count = await db.files.count_documents({"project_id": project_id})
    print(f"\n✓ Files for {project_id}: {files_count} documents")
    
    if files_count > 0:
        print("  First 5 files:")
        async for file in db.files.find({"project_id": project_id}).limit(5):
            print(f"   - {file['path']} ({file.get('language', 'unknown')})")
    else:
        print("  ⚠ No files found!")
    
    # 4. Check Code Blobs
    blobs_count = await db.code_blobs.count_documents({"file_id": {"$regex": f"^{project_id}:"}})
    print(f"\n✓ Code Blobs for {project_id}: {blobs_count} documents")
    
    # 5. Check Snapshots
    snapshots_count = await db.snapshots.count_documents({"project_id": project_id})
    print(f"\n✓ Snapshots for {project_id}: {snapshots_count} documents")
    
    # 6. Check Sandbox Sessions
    sandbox = await db.sandbox_sessions.find_one({"project_id": project_id})
    print(f"\n✓ Sandbox Session: {'Found' if sandbox else 'Not Found'}")
    
    if sandbox:
        print(f"  Sandbox ID: {sandbox.get('sandbox_id', 'N/A')}")
        print(f"  Status: {sandbox.get('status', 'N/A')}")
        print(f"  Preview URL: {sandbox.get('preview_url', 'N/A')}")
    else:
        print("  ⚠ No sandbox session found!")
    
    # 7. Verify Indexes
    print("\n=== INDEX VERIFICATION ===\n")
    
    for collection_name in ["projects", "files", "code_blobs", "scp_versions", "snapshots"]:
        indexes = await db[collection_name].index_information()
        print(f"✓ {collection_name}: {len(indexes)} indexes")
        for idx_name in indexes:
            if idx_name != "_id_":
                print(f"  - {idx_name}")
    
    print("\n=== VERIFICATION COMPLETE ===\n")
    
    # Summary
    all_good = True
    if projects_count == 0:
        all_good = False
        print("❌ No projects found in database")
    if scp_count == 0:
        all_good = False
        print("❌ No SCP versions found")
    if files_count == 0:
        all_good = False
        print("❌ No files found")
    if not sandbox:
        all_good = False
        print("❌ No sandbox session found")
    
    if all_good:
        print("✅ All checks passed! Database is healthy.")
    else:
        print("\n⚠️  Some checks failed. Please review above.")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(verify_database())
