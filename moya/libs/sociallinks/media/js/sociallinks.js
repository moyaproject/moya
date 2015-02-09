$(function(){
    function on_jsonrpc_error(id, response)
    {
        console.log("JSONRPC error", response);
    }
    sociallinks_rpc = new JSONRPC(sociallinks_jsonrpc_url, {"error": on_jsonrpc_error});
});

$('.moya-sociallinks-link .vote-box.authenticated .vote').click(function(){
    var $vote = $(this);
    var $vote_box = $vote.parent();
    var score = $vote_box.data('score');
    var link = $vote.data('link');

    if ($vote.hasClass('active'))
    {
        var vote = 0;
        $vote.removeClass('active');
    }
    else
    {
        var vote = parseInt($vote.data('vote'));
        $vote_box.find('.vote').removeClass('active');
        $vote.addClass('active');
    }
    var new_score = score + vote;
    $vote_box.find('.score').text(new_score);

    sociallinks_rpc.notify('vote', {"link": link, "score": vote});
});
