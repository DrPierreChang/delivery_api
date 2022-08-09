from __future__ import absolute_import

from datetime import datetime

from django.http import Http404, HttpResponseRedirect
from django.utils import timezone
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode
from django.views import generic

from dateutil import relativedelta

from radaro_utils.utils import get_date_format


class ObjectByTokenMixin(object):

    def dispatch(self, request, *args, **kwargs):
        uidb64 = kwargs['uidb64']
        self.token = kwargs['token']
        assert uidb64 is not None and self.token is not None
        try:
            # urlsafe_base64_decode() decodes to bytestring on Python 3
            self.uid = force_text(urlsafe_base64_decode(uidb64))
        except (TypeError, ValueError, OverflowError):
            raise Http404
        return super(ObjectByTokenMixin, self).dispatch(request, *args, **kwargs)


class GenericTimeFramedReport(generic.TemplateView):
    date_from = None
    date_to = None

    def dispatch(self, request, *args, **kwargs):
        date_to = request.GET.get('date_to', None)
        date_from = request.GET.get('date_from', None)
        date_format = get_date_format()

        self.date_to = datetime.strptime(date_to, date_format) if date_to else timezone.now().date()
        self.date_from = datetime.strptime(date_from, date_format) if date_from \
            else self.date_to + relativedelta.relativedelta(months=-1)
        return super(GenericTimeFramedReport, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(GenericTimeFramedReport, self).get_context_data(**kwargs)
        context['date_format'] = get_date_format()
        return context


class CustomHttpResponseRedirect(HttpResponseRedirect):
    """
    HTTP redirect response which does not cause automatic browser redirect
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self['Redirect-Url'] = self['Location']
        del self['Location']

    @property
    def url(self):
        return self['Redirect-Url']
