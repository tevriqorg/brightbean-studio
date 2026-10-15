from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.composer.models import Idea
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.workspaces.models import Workspace


class PXCaptureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="px-owner@example.com",
            password="testpass123",
            tos_accepted_at=timezone.now(),
        )
        self.org = Organization.objects.create(name="PX Test Org")
        self.workspace = Workspace.objects.create(organization=self.org, name="PX Test Workspace")
        OrgMembership.objects.create(
            user=self.user,
            organization=self.org,
            org_role=OrgMembership.OrgRole.OWNER,
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
        )
        self.client.force_login(self.user)
        self.create_url = reverse(
            "composer:idea_create",
            kwargs={"workspace_id": self.workspace.id},
        )

    @override_settings(PX_MODE=True)
    def test_px_capture_derives_title_from_raw_description(self):
        response = self.client.post(
            self.create_url,
            {"description": "  消费降级会不会形成一个自我强化的循环？   这是后面的补充。  "},
        )

        self.assertEqual(response.status_code, 204)
        idea = Idea.objects.get(workspace=self.workspace)
        self.assertTrue(idea.description.startswith("消费降级"))
        self.assertTrue(idea.title.startswith("消费降级会不会形成一个自我强化的循环？"))

    @override_settings(PX_MODE=False)
    def test_upstream_mode_still_requires_title(self):
        response = self.client.post(self.create_url, {"description": "raw only"})

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Idea.objects.filter(workspace=self.workspace).exists())
