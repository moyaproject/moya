(function($) {
    $.fn.moyaComments = function() {

        var $this = $(this);

        $this.find('form.moya-comment-reply-form,form.moya-comment-form').each(function(){
            var $form = $(this);
            var $submit_button = $form.find('input[type=submit]');
            var $text = $form.find('textarea[name=text]');
            var check_button = function()
            {
                var text = $text.val()
                if (text || text.replace(/(^[\s]+|[\s]+$)/g, ''))
                {
                    $submit_button.removeAttr('disabled');
                }
                else
                {
                    $submit_button.attr('disabled', 'disabled');
                }
            }
            $text.keyup(function(){
                check_button();
            });
            check_button();
        });

        $this.find('.moya-comment-actions .reply').click(function(){
            var $reply = $(this);
            var commentid = $reply.data('commentid');
            $this.find('form[name=' + commentid + ']').slideToggle();
            return false;
        });
        $this.find('.moya-comment .cancel').click(function(){
            var $cancel = $(this);
            var commentid = $cancel.data('commentid');
            var $form = $this.find('form[name=' + commentid + ']');
            $form.slideUp();
            return false;
        });
        if(window.location.hash)
        {
            if (window.location.hash.substr(0, 7))
            {
                var comment_id = window.location.hash.substr(8);
                $this.find('.moya-comment-' + comment_id).addClass('moya-highlighted-comment');
            }
        }
    };
})(jQuery);
