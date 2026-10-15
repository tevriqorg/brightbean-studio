from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.composer.models import Idea, Post
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

    @override_settings(PX_MODE=True)
    def test_px_create_page_renders_after_capture(self):
        Idea.objects.create(
            workspace=self.workspace,
            title="raw",
            description="raw idea",
            author=self.user,
        )
        response = self.client.get(
            reverse("composer:create_landing", kwargs={"workspace_id": self.workspace.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI 处理")

    @override_settings(
        PX_MODE=True,
        PX_LLM_URL="http://llm.example/v1",
        PX_LLM_MODEL="auto",
        PX_LLM_TIMEOUT=5.0,
    )
    @patch("apps.composer.views.httpx.post")
    def test_px_create_post_uses_ai_candidate_and_preserves_idea(self, mock_post):
        idea = Idea.objects.create(
            workspace=self.workspace,
            title="raw",
            description="AI跑得太快，我同时处理三个以上会话就跟不上了。",
            author=self.user,
        )
        llm_response = Mock()
        llm_response.raise_for_status.return_value = None
        llm_response.json.return_value = {
            "choices": [{"message": {"content": "AI太快，超过三个会话我就跟不上了。"}}]
        }
        mock_post.return_value = llm_response

        response = self.client.post(
            reverse(
                "composer:idea_create_post",
                kwargs={"workspace_id": self.workspace.id, "idea_id": idea.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        idea.refresh_from_db()
        self.assertEqual(
            idea.description,
            "AI跑得太快，我同时处理三个以上会话就跟不上了。",
        )
        post = Post.objects.get(id=idea.post_id)
        self.assertEqual(post.caption, "AI太快，超过三个会话我就跟不上了。")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "auto")
        self.assertIn("不添加用户没说过的信息", payload["messages"][0]["content"])
