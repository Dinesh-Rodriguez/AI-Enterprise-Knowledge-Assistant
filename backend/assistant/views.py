import json

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import StreamingHttpResponse
from rest_framework import generics, permissions, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from assistant.models import AuditEvent, Conversation, Document, DocumentChunk, Message, Workspace, WorkspaceSettings
from assistant.serializers import (
    AuditEventSerializer,
    ConversationSerializer,
    DocumentSerializer,
    DocumentChunkSerializer,
    FocusDocumentSerializer,
    MessageSerializer,
    RegisterSerializer,
    WorkspaceMemberSerializer,
    WorkspaceSettingsSerializer,
    WorkspaceSerializer,
)
from assistant.services.retrieval import compose_answer, retrieve_relevant_chunks
from assistant.services.providers import get_llm_provider
from assistant.tasks import index_document_task

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class LoginSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["username"] = user.username
        return token


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


class WorkspaceViewSet(viewsets.ModelViewSet):
    serializer_class = WorkspaceSerializer

    def get_queryset(self):
        return Workspace.objects.filter(Q(created_by=self.request.user) | Q(members__user=self.request.user)).distinct().order_by("-created_at")

    def perform_create(self, serializer):
        workspace = serializer.save(created_by=self.request.user)
        workspace.members.create(user=self.request.user, role="owner")
        WorkspaceSettings.objects.create(workspace=workspace)
        AuditEvent.objects.create(
            workspace=workspace,
            actor=self.request.user,
            action="workspace.created",
            target_type="workspace",
            target_id=str(workspace.id),
        )

    @action(detail=True, methods=["get", "patch"])
    def config(self, request, pk=None):
        workspace = self.get_object()
        if request.method == "GET":
            return Response(WorkspaceSettingsSerializer(workspace.settings).data)
        serializer = WorkspaceSettingsSerializer(workspace.settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def members(self, request, pk=None):
        workspace = self.get_object()
        return Response(WorkspaceMemberSerializer(workspace.members.all(), many=True).data)


class DocumentViewSet(viewsets.ModelViewSet):
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        queryset = Document.objects.filter(Q(workspace__created_by=self.request.user) | Q(workspace__members__user=self.request.user)).distinct().order_by("-created_at")
        workspace_id = self.request.query_params.get("workspace")
        if workspace_id:
            queryset = queryset.filter(workspace_id=workspace_id)
        return queryset

    def perform_create(self, serializer):
        workspace = serializer.validated_data["workspace"]
        self._assert_can_write(workspace)
        document = serializer.save()
        document.status = Document.Status.INDEXING
        document.progress = 0
        document.error_message = ""
        document.save(update_fields=["status", "progress", "error_message"])
        index_document(document.id)
        AuditEvent.objects.create(
            workspace=workspace,
            actor=self.request.user,
            action="document.uploaded",
            target_type="document",
            target_id=str(document.id),
        )

    @action(detail=True, methods=["get"])
    def focus(self, request, pk=None):
        document = self.get_object()
        page = request.query_params.get("page")
        chunks = document.chunks.all().order_by("page_number", "chunk_index")
        if page:
            chunks = chunks.filter(page_number=page)
        payload = FocusDocumentSerializer(document).data
        payload["chunks"] = DocumentChunkSerializer(chunks, many=True).data
        return Response(payload)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        document = self.get_object()
        self._assert_can_write(document.workspace)
        document.status = Document.Status.INDEXING
        document.progress = 0
        document.error_message = ""
        document.save(update_fields=["status", "progress", "error_message"])
        index_document(document.id)
        return Response(DocumentSerializer(document).data)

    @action(detail=True, methods=["post"])
    def summarize(self, request, pk=None):
        document = self.get_object()
        summary = summarize_document(document)
        return Response(summary)

    @action(detail=True, methods=["post"])
    def meeting_notes(self, request, pk=None):
        document = self.get_object()
        notes = generate_meeting_notes(document)
        return Response(notes)

    @action(detail=True, methods=["post"])
    def compare(self, request, pk=None):
        document = self.get_object()
        other_id = request.data.get("other_document_id")
        if not other_id:
            return Response({"detail": "other_document_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        other = Document.objects.get(id=other_id)
        self._assert_can_write(other.workspace)
        comparison = compare_documents(document, other)
        return Response(comparison)

    def _assert_can_write(self, workspace):
        if not can_write_workspace(workspace, self.request.user):
            raise PermissionDenied("You do not own this workspace.")


def index_document(document_id: int):
    # The packaged local deployment does not require Redis/Celery. Process the
    # document immediately so the user can ask questions without a worker.
    index_document_task(document_id)


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return Conversation.objects.filter(Q(workspace__created_by=self.request.user) | Q(workspace__members__user=self.request.user)).distinct().order_by("-created_at")

    def perform_create(self, serializer):
        workspace = serializer.validated_data["workspace"]
        self._assert_can_write(workspace)
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def ask(self, request, pk=None):
        conversation = self.get_object()
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"detail": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

        Message.objects.create(conversation=conversation, role=Message.Role.USER, content=question)
        try:
            hits = retrieve_relevant_chunks(conversation.workspace, question)
            result = compose_answer(question, hits)
        except Exception:
            result = {"answer": "I could not complete source search right now. Please try again after confirming the document is ready.", "citations": []}
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=result["answer"],
            citations=result["citations"],
        )
        return Response(
            {
                "message": MessageSerializer(message).data,
                "citations": result["citations"],
            }
        )

    @action(detail=True, methods=["post"])
    def stream_ask(self, request, pk=None):
        conversation = self.get_object()
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"detail": "question is required"}, status=status.HTTP_400_BAD_REQUEST)

        Message.objects.create(conversation=conversation, role=Message.Role.USER, content=question)
        try:
            hits = retrieve_relevant_chunks(conversation.workspace, question)
            result = compose_answer(question, hits)
        except Exception:
            result = {"answer": "I could not complete source search right now. Please try again after confirming the document is ready.", "citations": []}
        assistant_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=result["answer"],
            citations=result["citations"],
        )

        def stream():
            try:
                yield f"event: citations\ndata: {json.dumps(result['citations'])}\n\n"
                for token in result["answer"].split():
                    yield f"event: token\ndata: {json.dumps({'text': token + ' '})}\n\n"
                yield f"event: done\ndata: {json.dumps({'message_id': assistant_message.id})}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

        response = StreamingHttpResponse(stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _assert_can_write(self, workspace):
        if not can_write_workspace(workspace, self.request.user):
            raise PermissionDenied("You do not own this workspace.")


class HealthView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


def summarize_document(document: Document) -> dict:
    text = (document.extracted_text or "").strip()
    if not text:
        return {"summary": "No extracted text is available yet."}
    prompt = "Summarize this document in concise bullet points:\n\n" + text[:12000]
    summary = get_llm_provider().chat([{"role": "user", "content": prompt}])
    return {"summary": summary}


def generate_meeting_notes(document: Document) -> dict:
    text = (document.extracted_text or "").strip()
    if not text:
        return {"summary": "No transcript text is available yet.", "action_items": []}
    prompt = (
        "Turn this transcript into meeting notes with a short summary, decision list, and action items.\n\n"
        + text[:12000]
    )
    notes = get_llm_provider().chat([{"role": "user", "content": prompt}])
    return {"notes": notes}


def compare_documents(left: Document, right: Document) -> dict:
    left_text = (left.extracted_text or "").strip()[:8000]
    right_text = (right.extracted_text or "").strip()[:8000]
    prompt = (
        f"Compare these two documents.\n\nDocument A: {left.title}\n{left_text}\n\n"
        f"Document B: {right.title}\n{right_text}\n\n"
        "Give similarities, differences, and risks."
    )
    comparison = get_llm_provider().chat([{"role": "user", "content": prompt}])
    return {"comparison": comparison}


def can_write_workspace(workspace, user):
    if workspace.created_by_id == user.id:
        return True
    member = workspace.members.filter(user=user).first()
    return bool(member and member.role in {"owner", "admin"})
