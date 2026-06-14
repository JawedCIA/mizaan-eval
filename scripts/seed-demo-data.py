"""Seed script — Populates the database with sales performance demo data.

Run with: python scripts/seed-demo-data.py

Creates:
- A demo organization
- A demo user
- A "sales-call-v2" rubric with 4 dimensions
- Sample work items representing sales calls
"""

import asyncio
import os
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://mizaan:mizaan_dev@localhost:5432/mizaan",
)

DEMO_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEMO_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")

SALES_RUBRIC_DIMENSIONS = [
    {
        "name": "Communication Quality",
        "description": "Clarity, persuasiveness, and professionalism of communication",
        "weight": 0.25,
        "scoring_criteria": [
            "Clear articulation of value proposition",
            "Active listening and appropriate responses",
            "Professional tone and language",
            "Effective handling of objections",
        ],
    },
    {
        "name": "Business Impact",
        "description": "Direct revenue or pipeline impact of the interaction",
        "weight": 0.35,
        "scoring_criteria": [
            "Deal size or revenue generated",
            "Pipeline advancement (stage progression)",
            "New opportunities identified",
            "Strategic account development",
        ],
    },
    {
        "name": "Customer Relationship",
        "description": "Quality of relationship building and customer satisfaction",
        "weight": 0.20,
        "scoring_criteria": [
            "Rapport building effectiveness",
            "Understanding of customer needs",
            "Follow-up commitment and execution",
            "Trust and credibility established",
        ],
    },
    {
        "name": "Process Adherence",
        "description": "Following established sales methodology and CRM hygiene",
        "weight": 0.20,
        "scoring_criteria": [
            "Sales methodology followed (MEDDIC/SPIN/etc.)",
            "CRM updated with accurate information",
            "Next steps clearly defined",
            "Documentation quality",
        ],
    },
]

SAMPLE_WORK_ITEMS = [
    {
        "type": "sales-call",
        "title": "Q4 Enterprise Deal — Acme Corp",
        "description": """Sales call with Acme Corp VP of Engineering about our enterprise platform.
Call duration: 45 minutes.

Key points:
- Discussed their current pain points with manual scoring processes
- Presented ROI analysis showing 60% time savings
- VP expressed strong interest, requested a technical demo
- Identified 3 additional stakeholders for the buying committee
- Next step: Technical demo scheduled for next Tuesday
- Deal size: $120K ARR

Notes: Good discovery call. VP was engaged throughout and asked detailed questions
about our AI scoring methodology. Competitive situation with two other vendors.""",
        "context": {
            "client_tier": "enterprise",
            "deal_stage": "discovery",
            "deal_size": 120000,
            "competitors": ["VendorA", "VendorB"],
        },
    },
    {
        "type": "sales-call",
        "title": "SMB Renewal — TechStart Inc",
        "description": """Renewal call with TechStart Inc, existing customer on Growth plan.
Call duration: 20 minutes.

Key points:
- Customer happy with product, NPS 9/10
- Discussed upgrading to Business plan for additional rubric slots
- Customer budget cycle starts Q1, will revisit then
- No competitive threat identified
- Next step: Send upgrade proposal, follow up January 15

Notes: Straightforward renewal. Customer is a champion but needs budget approval
for the upgrade. Low risk of churn.""",
        "context": {
            "client_tier": "smb",
            "deal_stage": "renewal",
            "deal_size": 24000,
            "current_plan": "growth",
        },
    },
    {
        "type": "sales-call",
        "title": "Cold Outbound — FinServ Global",
        "description": """Initial outbound call to FinServ Global, Director of Operations.
Call duration: 12 minutes.

Key points:
- Reached the right contact after 3 attempts
- Brief pitch on AI scoring for compliance reviews
- Prospect was rushed, gave 5 minutes
- Some interest expressed but non-committal
- Next step: Send one-pager via email, follow up in 2 weeks

Notes: Tough cold call. Prospect is clearly busy. The compliance angle resonated
briefly but didn't have time to develop. Need to refine the cold pitch.""",
        "context": {
            "client_tier": "enterprise",
            "deal_stage": "prospecting",
            "deal_size": None,
            "outbound": True,
        },
    },
]


async def seed() -> None:
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        from sqlalchemy import text

        # Create demo org
        await session.execute(
            text("""
                INSERT INTO organizations (id, clerk_org_id, name, plan, llm_provider)
                VALUES (:id, :clerk_org_id, :name, :plan, :provider)
                ON CONFLICT (clerk_org_id) DO NOTHING
            """),
            {
                "id": str(DEMO_ORG_ID),
                "clerk_org_id": "org_demo",
                "name": "Demo Organization",
                "plan": "business",
                "provider": "ollama",
            },
        )

        # Create demo user
        await session.execute(
            text("""
                INSERT INTO users (id, clerk_user_id, email, name, role, tenant_id)
                VALUES (:id, :clerk_user_id, :email, :name, :role, :tenant_id)
                ON CONFLICT (clerk_user_id) DO NOTHING
            """),
            {
                "id": str(DEMO_USER_ID),
                "clerk_user_id": "user_demo",
                "email": "demo@mizaan.ai",
                "name": "Demo User",
                "role": "admin",
                "tenant_id": str(DEMO_ORG_ID),
            },
        )

        # Create sales rubric
        rubric_id = uuid.uuid4()
        await session.execute(
            text("""
                INSERT INTO rubrics (id, tenant_id, name, slug, description, current_version)
                VALUES (:id, :tenant_id, :name, :slug, :desc, :ver)
                ON CONFLICT ON CONSTRAINT uq_rubrics_tenant_slug DO NOTHING
            """),
            {
                "id": str(rubric_id),
                "tenant_id": str(DEMO_ORG_ID),
                "name": "Sales Call Evaluation v2",
                "slug": "sales-call-v2",
                "desc": "Comprehensive sales call evaluation rubric with 4 weighted dimensions",
                "ver": 1,
            },
        )

        # Create rubric version
        import json

        await session.execute(
            text("""
                INSERT INTO rubric_versions (id, rubric_id, version, dimensions, change_notes)
                VALUES (:id, :rubric_id, :version, cast(:dims as jsonb), :notes)
                ON CONFLICT ON CONSTRAINT uq_rubric_versions_rubric_version DO NOTHING
            """),
            {
                "id": str(uuid.uuid4()),
                "rubric_id": str(rubric_id),
                "version": 1,
                "dims": json.dumps(SALES_RUBRIC_DIMENSIONS),
                "notes": "Initial version with 4 weighted dimensions",
            },
        )

        # Create sample work items
        for item in SAMPLE_WORK_ITEMS:
            await session.execute(
                text("""
                    INSERT INTO work_items (id, tenant_id, work_item_type, title, description, context, source)
                    VALUES (:id, :tenant_id, :type, :title, :desc, cast(:ctx as jsonb), :source)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(DEMO_ORG_ID),
                    "type": item["type"],
                    "title": item["title"],
                    "desc": item["description"],
                    "ctx": json.dumps(item["context"]),
                    "source": "seed",
                },
            )

        await session.commit()
        print("Demo data seeded successfully!")
        print(f"  Organization: {DEMO_ORG_ID}")
        print(f"  User: {DEMO_USER_ID}")
        print(f"  Rubric: sales-call-v2 ({rubric_id})")
        print(f"  Work items: {len(SAMPLE_WORK_ITEMS)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
