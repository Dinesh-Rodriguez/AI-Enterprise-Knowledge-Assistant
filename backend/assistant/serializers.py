from django.contrib.auth import get_user_model
from rest_framework import serializers

from assistant.models import (
    AuditEvent,
    Conversation,
    Document,
    DocumentChunk,
    Message,
    Workspace,
    WorkspaceMember,
    WorkspaceSettings,
)

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")

    def create(self, validated_data):
        user = User(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
        )
        user.set_password(validated_data["password"])
        user.save()
        return user


class WorkspaceSerializer(serializers.ModelSerializer):
    settings = serializers.SerializerMethodField()
    members_count = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ("id", "name", "description", "created_at", "settings", "members_count")

    def get_settings(self, obj):
        settings = getattr(obj, "settings", None)
        if not settings:
            return None
        return {
            "llm_provider": settings.llm_provider,
            "embedding_provider": settings.embedding_provider,
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
        }

    def get_members_count(self, obj):
        return obj.members.count()


class WorkspaceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkspaceSettings
        fields = ("llm_provider", "embedding_provider", "llm_model", "embedding_model")


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = WorkspaceMember
        fields = ("id", "user", "username", "role", "created_at")


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ("id", "actor", "action", "target_type", "target_id", "metadata", "created_at")


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ("id", "workspace", "title", "file", "mime_type", "status", "progress", "error_message", "created_at", "updated_at")
        read_only_fields = ("status", "progress", "error_message", "created_at", "updated_at", "mime_type")


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = ("id", "page_number", "chunk_index", "content", "citation_label")


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ("id", "role", "content", "citations", "created_at")


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ("id", "workspace", "title", "created_at", "messages")


class FocusDocumentSerializer(serializers.ModelSerializer):
    chunks = DocumentChunkSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = ("id", "workspace", "title", "status", "chunks")
