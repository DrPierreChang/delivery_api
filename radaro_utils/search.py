from watson import search as watson
from watson.models import SearchEntry


def watson_index_bulk_update(objs):
    search_engine = watson.default_search_engine

    def iter_search_entries(objs):
        for obj in objs:
            for search_entry in search_engine._update_obj_index_iter(obj):
                yield search_entry

    watson._bulk_save_search_entries(iter_search_entries(objs))


def update_search_entries(from_=0, to_=10000):
    search_engine_ = watson.default_search_engine
    local_refreshed_count = [0, 0]

    registered_models = [model.__name__.lower() for model in search_engine_.get_registered_models()]

    def iter_search_entries():
        for search_entry in SearchEntry.objects.filter(id__gte=from_, id__lte=to_, content_type__model__in=registered_models).all():
            obj = search_entry.object
            if not obj:
                local_refreshed_count[1] += 1
                continue
            for search_entry in search_engine_._update_obj_index_iter(obj):
                yield search_entry
            local_refreshed_count[0] += 1
        print("Refreshed {0} search entry(s), not refreshed {1}".format(*local_refreshed_count))

    watson._bulk_save_search_entries(iter_search_entries())
