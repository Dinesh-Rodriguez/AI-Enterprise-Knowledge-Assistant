from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from assistant.views import ConversationViewSet, CurrentUserView, DocumentViewSet, HealthView, LoginView, RegisterView, WorkspaceViewSet

router = DefaultRouter()
router.register(r"workspaces", WorkspaceViewSet, basename="workspace")
router.register(r"documents", DocumentViewSet, basename="document")
router.register(r"conversations", ConversationViewSet, basename="conversation")

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("auth/register/", RegisterView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("auth/me/", CurrentUserView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("", include(router.urls)),
]
