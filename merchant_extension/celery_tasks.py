from delivery.celery import app


@app.task()
def handle_wrong_answers_sod_checklist(result_checklist_id):
    from merchant_extension.models import ResultChecklist
    checklist = ResultChecklist.objects.get(id=result_checklist_id)

    merchant = checklist.checklist_merchant
    if not merchant.sod_checklist_email:
        return

    wrong_answers = checklist.result_answers.annotate_correct_answer().order_by('question__consecutive_number') \
        .filter(correct_answer=False)
    context = {
        'driver': checklist.driver,
        'date': checklist.created_at.astimezone(merchant.timezone).strftime('%B %d, %Y'),
    }
    for answer in wrong_answers:
        attachments = list(answer.answer_attachments_generator())
        extra_context = dict(answer=answer, has_attachments=bool(attachments), **context)
        merchant.send_sod_issue_email(
            attachments=attachments,
            email=merchant.sod_checklist_email,
            extra_context=extra_context,
        )


@app.task()
def handle_wrong_answers_eod_checklist(result_checklist_id):
    from merchant_extension.models import ResultChecklist
    checklist = ResultChecklist.objects.get(id=result_checklist_id)

    merchant = checklist.checklist_merchant
    if not merchant.eod_checklist_email:
        return

    wrong_answers = checklist.result_answers.annotate_correct_answer().order_by('question__consecutive_number') \
        .filter(correct_answer=False)
    context = {
        'driver': checklist.driver,
        'date': checklist.created_at.astimezone(merchant.timezone).strftime('%B %d, %Y'),
    }
    for answer in wrong_answers:
        attachments = list(answer.answer_attachments_generator())
        extra_context = dict(answer=answer, has_attachments=bool(attachments), **context)
        merchant.send_eod_issue_email(
            attachments=attachments,
            email=merchant.eod_checklist_email,
            extra_context=extra_context,
        )
