import functools
import server_logger

logger = server_logger.get()

##### Decorators for event handlers #####

def validate_payload_fields(fields):
    """Decorator that checks for existence of fields in the payload passed to an event handler"""
    def _validate_payload_fields(func):
        @functools.wraps(func)
        def wrapper_validate_payload_fields(*args, **kwargs):
            if len(args) < 2 and ('sid' not in kwargs or 'payload' not in kwargs):
                return
            if len(args) >= 2:
                sid, payload = args[0], args[1]
            else:
                sid = kwargs['sid']
                payload = kwargs['payload']

            if type(payload) != dict:
                logger.error(f'Expected type={dict}, found type={type(payload)}')
                return

            fields_not_present = []
            for f in fields:
                if f not in payload:
                    fields_not_present.append(f)
            if fields_not_present:
                logger.error(f'sid={sid} called event_handler="{func.__name__}" but missing fields={fields_not_present}')
                return

            # all validation passed, run actual event handler
            return func(*args, **kwargs)
        return wrapper_validate_payload_fields
    return _validate_payload_fields

def log_exception(func):
    """Decorator that captures exceptions in event handlers and passes them to the logger"""
    @functools.wraps(func)
    def wrapper_log_exception(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            logger.exception(f'Exception occured in event_handler={func.__name__}')
    return wrapper_log_exception

