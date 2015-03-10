
$(function(){

    $('.moya-admin-datetime-input').each(function(){
        var $input = $(this);
        var $date = $input.find('.moya-admin-date');
        var $time = $input.find('.moya-admin-time');
        var $datetime = $input.find('.moya-admin-datetime');
        function on_change()
        {
            var date = $date.val();
            var time = $time.val();
            if (date || time)
            {
                $datetime.val(date + 'T' + time);
            }
            else
            {
                $datetime.val('');
            }
        }
        $input.find('.moya-admin-date').change(function(){
            on_change();
        });

        $input.find('.moya-admin-time').change(function(){
            on_change();
        });
        $input.find('.moya-admin-datetime-now').click(function(){
            var now = new Date();
            function pad(s)
            {
                if (('' + s).length == 1)
                {
                    return '0' + s;
                }
                return s;
            }

            var now_date = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
            var now_time = pad(now.getHours()) + ':' + pad(now.getMinutes());
            $date.val(now_date);
            $time.val(now_time);
            on_change();
        });
        $input.find('.moya-admin-datetime-clear').click(function(){
            $date.val('');
            $time.val('');
            on_change();
        });
        $input.find('.moya-admin-datetime-settime').click(function(){
            var t = $(this).data('time');
            $time.val(t);
            on_change();
        });
    });

    $('.moya-admin-date-input').each(function(){
        var $input = $(this);
        var $date = $input.find('.moya-admin-date');
        var $datevalue = $input.find('.moya-admin-date-value');
        function on_change()
        {
            var date = $date.val();
            if (date)
            {
                $datevalue.val(date);
            }
            else
            {
                $datevalue.val('');
            }
        }
        $input.find('.moya-admin-date').change(function(){
            on_change();
        });

        $input.find('.moya-admin-date-now').click(function(){
            var now = new Date();
            function pad(s)
            {
                if (('' + s).length == 1)
                {
                    return '0' + s;
                }
                return s;
            }
            var now_date = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate());
            $date.val(now_date);
            on_change();
        });
        $input.find('.moya-admin-date-clear').click(function(){
            $date.val('');
            $time.val('');
            on_change();
        });
    });

    $('form.admin-table input[name=q]').keydown(function(){
        $(this).parents('.admin-table-query').find('.reset-search').hide();
    });

    function check_action(){
        var $select = $('form.admin-table select.form-control');
        var value = $select.val();
        var $button = $select.parent('.admin-table-actions').find('button');
        if(value)
        {
            $button.prop('disabled', false);
        }
        else
        {
            $button.prop('disabled', true);
        }

    }

    $('form.admin-table select.form-control').change(check_action);
    check_action();

});


function on_check(field, checked, item)
{
    var $field = $("form.moya-admin-form input[name=" + field + "]");
    var val = $field.val();
    var changes = $field.data('changes');
    if (checked)
    {
        changes[item] = '+';
    }
    else
    {
        changes[item] = '-';
    }
    var added = [];
    var removed = [];
    for(var item in changes)
    {
        item = parseInt(item);
        if (changes[item] == '+')
        {
            added.push(item);
        }
        else
        {
            removed.push(item);
        }
    }
    $field.val(JSON.stringify({'removed': removed, 'added': added}));
}

function on_radio_check(field, checked, item)
{
    var $field = $("form.moya-admin-form input[name=" + field + "]");
    $field.val(item);
}

function shade_picker(field, shade)
{
    var $field = $("form.moya-admin-form input[name=" + field + "]");
    var $picker = $field.parents('.admin-picker-container');
    if (shade)
    {
        $picker.find('.admin-picker-shade').css('visibility', 'visible');
    }
    else
    {
        $picker.find('.admin-picker-shade').css('visibility', 'hidden');
    }
}

function set_checked(field, item, $row)
{
    var $field = $("form.moya-admin-form input[name=" + field + "]");
    var val = $field.val();
    var selected = $field.data('selected') || [];
    var changes = $field.data('changes') || {};
    var checked = selected.indexOf(item) != -1;
    var original = checked;
    if (changes[item])
    {
        checked = changes[item] == '+';
    }
    if (original)
    {
        $row.addClass('success');
    }
    if(checked)
    {
        $row.addClass('warning');
        $row.find('input.check-row').prop('checked', true);
    }
    return checked;
}

function set_checked_radio(field, item, $row)
{
    var $field = $("form.moya-admin-form input[name=" + field + "]");
    var val = $field.val();
    var checked = val == item;
    if(checked)
    {
        $row.addClass('warning');
        $row.find('input.check-row').prop('checked', true);
    }
}


function load_page(url)
{
    if(!url)
    {
        return;
    }
    var field = $('body').data('field');
    parent.shade_picker(field, true);
    $('.moya-admin-content-column').load(url + ' .admin-table-picker', function(response, status, jqXHR){
        parent.shade_picker(field, false);
        if(status=='success')
        {
            rebind($('.moya-admin-content-column'));
        }
    });
}

function rebind(selector)
{
    if(!selector)
    {
        var $selector = $('body');
    }
    else
    {
        var $selector = selector;
    }

    $selector.find('.picker-control').each(function(){
        var $picker_control = $(this);
        var field = $picker_control.data('field');
        $(this).find('button.picker-clear').unbind('click').click(function(e){
            $picker_control.addClass('null-object');
            $picker_control.find('#' + field).val('');
            $picker_control.find('iframe').attr('src', function(i, val) { return val; });
        });
    });

    $selector.find('.admin-table-picker').each(function(){
        var $picker = $(this);

        $picker.find('a').unbind('click').click(function(e){
            e.preventDefault();
            var $link = $(this);
            var url = $link.attr('href');
            load_page(url);
        });

        $picker.unbind('submit').submit(function(e){
            e.preventDefault();
            var url = '?' + $(this).serialize();
            load_page(url);
        });
    });

    $selector.find('.admin-table-picker.picker-many').each(function(){
        var $picker = $(this);

        $picker.find('.moya-admin-table-checkbox.check-row').unbind('change').change(function(e){
            var item = parseInt($(this).val());
            var checked = this.checked;
            var field = $('body').data('field');
            parent.on_check(field, checked, item);
        });

        var row_ids = [];
        $picker.find('tr.data-row').each(function(){
            var $row = $(this);
            var row_id = $row.data('id');
            var field = $('body').data('field');

            parent.set_checked(field, row_id, $row);

        });
    });

    $selector.find('.admin-table-picker.picker-single').each(function(){
        var $picker = $(this);

        $picker.find('.moya-admin-table-checkbox.check-row').unbind('change').change(function(e){
            var item = parseInt($(this).val());
            var checked = this.checked;
            var field = $('body').data('field');
            parent.on_radio_check(field, checked, item);
        });

        $picker.find('tr.data-row').each(function(){
            var $row = $(this);
            var row_id = $row.data('id');
            var field = $('body').data('field');
            parent.set_checked_radio(field, row_id, $row);
        });

    });

    $selector.find('table.moya-admin-table tr input.check-row').change(function(){
        var $check = $(this);
        var checked = $check.is(':checked');
        var $row = $check.parents('tr');
        if ($check.attr('type') == 'radio')
        {
            $selector.find('tr').removeClass('warning');
        }
        $row.toggleClass('warning', checked);
    });

    $selector.find('table.moya-admin-table th input.check-all').change(function(){
        var $check = $(this);
        var checked = $check.is(':checked');
        var $rows = $check.parents('table.moya-admin-table').find('tr.data-row');
        if (checked)
        {
            $rows.toggleClass('warning', checked);
            $rows.find('input.check-row:not(:checked)').click();
        }
        else
        {
            $rows.toggleClass('warning', checked);
            $rows.find('input.check-row:checked').click();
        }
    });
    $('button.show-picker').click(function(){
        var $button = $(this);
        var show = $button.data('show');
        $('#' + show).slideToggle();
    });

}


$(function(){
    rebind();
});