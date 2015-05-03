/* JS 'class' to make a JSRPC interface for a given url */


function JSONRPCBatch()
{
    var self = this
    self.requests = [];

    self.call = function(method, params)
    {
        var call = [false, method, params];
        self.requests.push(call)
    }
    self.notify = function(method, params)
    {
        var call = [true, method, params];
        self.requests.push(call);
    }
    return self;
}


function JSONRPC(url, options)
{
    var self = this;
    var rpc_id = 1;

    function success(result) {};
    function error(response) {};
    function failure(jqXHR, textStatus, errorThrown) {};
    function complete() {};
    function tasks() {};

    var options = options || {};
    self.success = options.success || success;
    self.error = options.error || error;
    self.failure = options.failure || failure;
    self.complete = options.complete || complete;
    self.tasks = options.tasks || tasks;

    self.active = 0;

    self.call = function(method, params, success, callbacks)
    {
        var call_id = rpc_id;
        var rpc_evelope = {jsonrpc:"2.0",
                           method:method,
                           params:params,
                           id:call_id};
        var rpc_json = JSON.stringify(rpc_evelope);
        var callbacks = callbacks || {};
        rpc_id += 1;
        self.active += 1;
        self.tasks(self.active);
        var call = {
            rpc: self,
            method: method,
            params: params,
            id: rpc_id
        };
        jQuery.ajax(url,
        {
            type:"POST",
            dataType:"json",
            processData:true,
            data:rpc_json,
            success:function(remote)
            {
                self.active -= 1;
                self.tasks(self.active);
                (callbacks.complete || self.complete)();
                if (remote.error)
                {
                    (callbacks.error || self.error)(remote.id, remote.error);
                }
                else
                {
                    (success || callbacks.success || self.success)(remote["result"]);
                }
            },
            error:function(jqXHR, textStatus, errorThrown)
            {
                self.active -= 1;
                self.tasks(self.active);
                (callbacks.complete || self.complete).call();
                (callbacks.failure || self.failure)(jqXHR, textStatus, errorThrown);
            }
        });
    }

    self.notify = function(method, params, success, callbacks)
    {
        var callbacks = callbacks || {};
        var rpc_evelope = {jsonrpc:"2.0",
                           method:method,
                           params:params};
        var rpc_json = JSON.stringify(rpc_evelope);
        self.active += 1;
        var call = {
            rpc: self,
            method: method,
            params: params
        };
        jQuery.ajax(url,
        {
            type:"POST",
            dataType:"json",
            processData:true,
            data:rpc_json,
            success:function(remote)
            {
                self.active -= 1;
                (callbacks.complete || self.complete)();
                if (remote['error'])
                {
                    (callbacks.error || self.error)(remote.id, remote.error);
                }
                else
                {
                    (success || callbacks.success || self.success)();
                }
            },
            error:function(jqXHR, textStatus, errorThrown)
            {
                self.active -= 1;
                (callbacks.complete || self.complete)();
                (callbacks.failure || self.failure).call(jqXHR, textStatus, errorThrown);
            }
        });
    }

    self.createBatch = function()
    {
        var batch = new JSONRPCBatch();
        return batch;
    }

    self.batch = function(batch, callbacks)
    {
        var requests = [];
        $.each(batch.requests, function(i, req){
            var notification = req[0];
            var method = req[1];
            var params = req[2];
            var rpc_envelope = {jsonrpc:"2.0",
                                method:method,
                                params:params};
            if (!notification)
            {
                rpc_envelope["id"] = rpc_id;
            }
            requests.push(rpc_envelope);
            rpc_id += 1;
        });

        var rpc_json = JSON.stringify(requests);
        jQuery.ajax(url,
        {
            type:"POST",
            dataType:"json",
            processData:false,
            data:rpc_json,
            success:function(remote)
            {
                self.active -= 1;
                (callbacks.complete || self.complete)();
                $.each(remote, function(i, response){
                    if (response.error)
                    {
                        (callbacks.error || self.error)(response.error);
                    }
                    else
                    {
                        (callbacks.success || self.success)(response.result);
                    }
                });
            },
            error:function(remote)
            {
                self.active -= 1;
                (callbacks.complete || self.complete)();
                (callbacks.failure || self.failure)(jqXHR, textStatus, errorThrown);
            }
        });
    }

    return this;
}