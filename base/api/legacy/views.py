from __future__ import absolute_import

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import FormView

from base.forms import EmployeeForm
from base.models import Invite
from radaro_utils.views import ObjectByTokenMixin
from reporting.models import Event
from reporting.signals import send_create_event_signal


@method_decorator(never_cache, name='dispatch')
class InviteView(ObjectByTokenMixin, FormView):
    template_name = 'invitations/invite_confirm.html'
    form_class = EmployeeForm

    def get_context_data(self, **kwargs):
        context = super(InviteView, self).get_context_data(**kwargs)

        if self.invite and not self.invite.invited:
            valid_link = True
            title = 'You accepted invitation!'
        else:
            valid_link = False
            title = 'Invitation was not found.'
        context.update({
            'title': title,
            'valid_link': valid_link,
        })
        return context

    def form_valid(self, form):
        new_user = form.save(commit=False)
        new_user.merchant = self.invite.merchant
        new_user.is_confirmed = True
        new_user.save()
        new_user.set_merchant_position(self.invite.position)

        self.invite.invited = new_user
        self.invite.save()
        event = Event.generate_event(self,
                                     initiator=new_user,
                                     field='invited',
                                     new_value=new_user,
                                     object=self.invite,
                                     event=Event.CHANGED)
        send_create_event_signal(events=[event])
        return redirect(reverse('invite_done'))

    def get_initial(self):
        initial = super(InviteView, self).get_initial()
        self.invite = get_object_or_404(Invite, pk=self.uid, token=self.token)

        if self.invite:
            initial.update({'email': self.invite.email, 'phone': self.invite.phone})
        return initial


def invite_done(request, template_name='invitations/invite_done.html', extra_context=None):
    return render(request, template_name, extra_context)
