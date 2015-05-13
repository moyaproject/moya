(function($) {

    $.fn.moyaSelect = function(options) {

        var options = options || {};
        var UP=38;
        var DOWN=40;
        var RETURN=13;
        var ESCAPE=27;
        var TAB = 9;

        var $this = $(this);
        var max_result = $this.data('count') - 1;

        var selection = -1;

        var $input = $this.find('input');
        var $options = $this.find('.moya-widgets-select')

        var $active = $this.find('.moya-widgets-option.active');
        if($active.length)
        {
            selection = parseInt($active.data('index'));
        }

        function update_height()
        {
            var $o = $options.clone();
            $('body').append($o);
            var height = 0;
            $o.find('.moya-widgets-option').each(function(i, el){
                if(i>=10)
                {
                    return false;
                }
                height += $(el).outerHeight();
            });
            var gutter = $o.outerHeight() - $o.innerHeight();
            height += gutter;
            $options.css('max-height', height + 'px');
            $o.remove();
        }

        $input.focus(function(e){
            $this.addClass('focused');
        });

        $input.blur(function(e){
            $this.removeClass('focused');
        });

        $this.find('.moya-widgets-option').click(function(e){
            e.preventDefault();
            var $option = $(this);
            $this.find('.moya-widgets-option').removeClass('active');
            $option.addClass('active');
            selection = $option.data('index');
            var value = $option.data('value');
            $input.val(value);
            $input.focus();
        });

        function refresh_selection()
        {
            $this.find('.moya-widgets-option').removeClass('active');
            $this.find('.moya-widgets-option.option-' + selection).addClass('active');
            var $active = $this.find('.moya-widgets-option.active');
            var value = $active.data('value');

            if (!$active.length)
            {
                return;
            }
            $input.val(value);
            var row_h = $active.outerHeight();
            var container_h = $options.height();
            var scroll = $options.scrollTop();
            var y = $active.offset().top - $options.offset().top + scroll - 1;

            if (y - scroll + row_h > container_h)
            {
                $options.scrollTop(y - container_h + row_h);
            }
            else if (y - scroll < 0)
            {
                $options.scrollTop(y);
            }
        }

        $input.keydown(function(e)
        {
            if (e.which==UP)
            {
                if (selection > 0)
                {
                    selection -= 1;
                    refresh_selection();
                }
                e.preventDefault();
            }
            else if (e.which==DOWN)
            {
                if (selection == -1)
                {
                    selection = 0;
                    refresh_selection();
                }
                else if (selection < max_result)
                {
                    selection += 1;
                    refresh_selection();
                }
                e.preventDefault();
            }
            else if (e.which==RETURN)
            {
                if(!$results.is(':visible'))
                {
                    return;
                }
                $results.hide();
                e.preventDefault();
                if(selection >= 0)
                {
                    var value = $results.find('.selection.active').data('value');
                    if(value)
                    {
                        $input.val(value);
                        selection = -1;
                        display_search = null;
                    }
                }

            }
        });

        update_height();
        refresh_selection();
    }

})(jQuery);
