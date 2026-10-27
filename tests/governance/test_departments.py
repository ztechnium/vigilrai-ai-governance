"""Default organization departments and membership assignment."""

from uuid import UUID

from rai_gateway.governance.domain import GovernanceRole
from rai_gateway.governance.service import GovernanceService


def test_default_departments_are_seeded_once(db_session, test_organization):
    service = GovernanceService(db_session)
    first = service.list_departments()
    second = service.list_departments()

    assert [item["name"] for item in first] == [
        "Marketing",
        "Management",
        "IT & Tech",
        "Sales",
        "R&D",
        "Accounts",
        "Security",
    ]
    assert [item["id"] for item in second] == [item["id"] for item in first]
    assert first[0]["description"]


def test_membership_can_be_placed_in_a_department(db_session, test_organization):
    service = GovernanceService(db_session)
    marketing = service.list_departments()[0]

    membership = service.create_membership(
        test_organization.id,
        user_id="user-marketing",
        role=GovernanceRole.RAI_OFFICER.value,
        created_by="tester",
        department_id=UUID(marketing["id"]),
    )

    assert membership["department_id"] == marketing["id"]
    assert membership["department_name"] == "Marketing"

    listed = service.list_memberships(test_organization.id)
    assert listed[0]["department_name"] == "Marketing"
