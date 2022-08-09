
def create_document_event(initiator, instance, document):
    from reporting.signals import create_event
    from tasks.signal_receivers.concatenated_order import co_auto_processing

    from ..api.legacy.serializers.documents import OrderConfirmationDocumentSerializer

    # The webhook of the uploaded document is in a non-standard format
    # and should not be called via OrderDeltaSerializer.
    old_dict = {'order_confirmation_documents': []}
    new_dict = {'order_confirmation_documents': [OrderConfirmationDocumentSerializer(instance=document).data]}
    create_event(old_dict, new_dict, initiator=initiator, instance=instance, sender=co_auto_processing)
