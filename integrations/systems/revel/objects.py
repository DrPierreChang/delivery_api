from integrations.systems.interfaces import CustomerInterface, ObjectFromDict, OrderInterface


class Field(object):
    def __init__(self, model, default=None):
        self._model = model
        self._field_name = model.__class__.__name__.lower()
        self._default_value = default

    def __get__(self, instance, owner):
        return getattr(instance, self._field_name, self._default_value)

    def __set__(self, instance, value):
        setattr(instance, self._field_name, value)


class ForeignKey(Field):
    def __set__(self, instance, value):
        if isinstance(value, dict):
            super(ForeignKey, self).__set__(instance, self._model.build_from_dict(value))
        elif value is None or isinstance(value, self._model) or isinstance(value, str):
            super(ForeignKey, self).__set__(instance, value)
        else:
            raise ValueError("You must provide a %s object or a dict (%s)" % (self._model.__class__.__name__, value))


class Customer(ObjectFromDict, CustomerInterface):
    """
        You can get list of all fields at 49 page of "Revel API 1.01.1424.pdf"
    """

    url = '/resources/Customer/'

    uuid = ''  # Blank - True, Null - False

    phone_number = ''  # Blank - True, Null - True
    first_name = ''  # Blank - False, Null - False
    last_name = ''  # Blank - False, Null - False
    email = ''  # Blank - False, Null - True

    company_name = ''  # Blank - False, Null - True

    address = ''
    city = ''
    state = ''
    zipcode = ''

    notes = ''

    def get_name(self):
        return "%s %s" % (self.first_name, self.last_name)

    def get_phone(self):
        return self.phone_number or ''

    def get_email(self):
        return self.email or ''


class Order(ObjectFromDict, OrderInterface):
    """
        You can get list of all fields at 158 page of "Revel API 1.01.1424.pdf"
    """
    url = '/resources/Order/'

    gratuity = 0.0  # Blank - False, Null - True

    id = 0  # Blank - True, Null - False
    local_id = 0  # Blank - False, Null - True
    uuid = ''  # Blank - True, Null - False

    delivery_distance = 0  # Blank - False, Null - True
    asap = False  # Blank - True, Null - False

    pickup_time = ''  # Blank - False, Null - True
    created_date = ''  # Blank - False, Null - False

    notes = ''

    exp_date = None

    registry_data = ''

    customer = ForeignKey(Customer, default=None)  # Blank - True, Null - True

    def get_title(self):
        return "Not provided"

    def get_comment(self):
        return self.customer.notes

    def get_deliver_before(self):
        return self.exp_date
