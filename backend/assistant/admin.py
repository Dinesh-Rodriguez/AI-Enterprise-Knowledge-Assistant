from django.contrib import admin

from assistant.models import Conversation, Document, DocumentChunk, Message, Workspace

admin.site.register(Workspace)
admin.site.register(Document)
admin.site.register(DocumentChunk)
admin.site.register(Conversation)
admin.site.register(Message)
