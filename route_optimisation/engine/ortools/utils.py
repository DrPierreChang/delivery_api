def prepare_capacity(capacity):
    # Ortools only supports integer capacities.
    # Therefore, this hack is used here so that several numbers after the decimal point are also supported.
    return int(capacity * 1000) if capacity is not None else None


def extract_capacity(prepared_capacity):
    return float(prepared_capacity) / 1000 if prepared_capacity is not None else None
