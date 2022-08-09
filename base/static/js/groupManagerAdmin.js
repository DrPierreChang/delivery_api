(function($) {
    $(document).ready(function () {
        let change_url = window.location;
        let url = change_url.protocol + "//" + change_url.host + '/admin/group-manager/merchants' + "?";

        let role = $('#id_role').val();
        let merchant_ids = $('#id_merchants').val();
        let sub_brand_ids = $('#id_sub_brandings').val();

        $.ajax({
            url: url,
            data: {
                'role': role,
                'merchant_ids': merchant_ids,
                'sub_brand_ids': sub_brand_ids,
                'document_load': true
            },
            success: function (data) {
                if (data.merchant_select_disabled) {
                    disable_merchant_multiselect()
                }

                if (data.sub_brand_select_disabled) {
                    disable_sub_brand_multiselect()
                } else {
                    fill_sub_brandings(data)
                }
            }
        });

        $('#id_role').on('change', function () {
            let role = $(this).val();
            $.ajax({
                url: url,
                data: {
                    'role': role,
                },
                success: function (data) {
                    if (data.merchant_select_disabled) {
                        disable_merchant_multiselect()
                    } else {
                        $("#id_merchants").empty().attr('disabled', false);
                        $.each(data.merchants, function(index, value) {
                            $("#id_merchants").append($('<option>', { value : value.id })
                                .text(value.name));
                        });
                    }

                    if (data.sub_brand_select_disabled) {
                        disable_sub_brand_multiselect()
                    } else {
                        $("#id_show_only_sub_branding_jobs").attr('disabled', false);
                        $("#id_sub_brandings").attr('disabled', false);
                        fill_sub_brandings(data)
                    }
                }
            });
        });

        $('#id_merchants').on('change', function () {
            let role = $('#id_role').val();
            let merchant_ids = $(this).val();
            let sub_brand_ids = $('#id_sub_brandings').val();
            $.ajax({
                url: url,
                data: {
                    'role': role,
                    'merchant_ids': merchant_ids,
                    'sub_brand_ids': sub_brand_ids,
                },
                success: function (data) {
                    if (!data.sub_brand_select_disabled) {
                        fill_sub_brandings(data)
                    }
                }
            });
        });

        function disable_merchant_multiselect() {
            $("#id_merchants").empty().attr('disabled', true);
        }

        function disable_sub_brand_multiselect() {
            $("#id_sub_brandings").empty().attr('disabled', true);
            $("#id_show_only_sub_branding_jobs").attr('disabled', true);
        }

        function fill_sub_brandings(data) {
            $("#id_sub_brandings").empty();
            $.each(data.sub_brandings, function(index, value) {
                $("#id_sub_brandings").append($('<option>', { value : value.id })
                    .text(value.name)
                    .attr('selected', value.chosen));
            });
        }
    });
})(django.jQuery);
