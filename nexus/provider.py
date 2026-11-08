"""Only trusted, fixed local Ollama endpoint. One provider call at a time."""
from threading import Lock, Timer
import socket
import time
import json
import httpx
from .schemas import Plan

_inference_lock = Lock()


class OllamaProvider:
    def __init__(self, settings):
        self.settings = settings
        self.checkpoint = None
        self.progress = None
        self.last_metrics = {}

    def _chat(self, system, prompt, tokens=500, tools=None, output_schema=None):
        started = time.monotonic()
        self.last_metrics = {}
        deadline = started + self.settings.model_timeout
        payload = dict(model=self.settings.model, stream=True, think=False,
                       keep_alive='30s', options=dict(num_ctx=self.settings.context_size,
                       num_predict=min(tokens, 900), temperature=0.1,
                       num_batch=self.settings.model_batch, num_thread=self.settings.model_threads),
                       messages=[dict(role='system', content=system[:1800]), dict(role='user', content=prompt[:6500])])
        if tools:
            payload['tools'] = tools
        elif output_schema:
            payload['format'] = output_schema
        elif 'JSON' in system and ('Return' in system or 'return' in system):
            payload['format'] = 'json'
        message = dict(role='assistant', content='')

        def check():
            if self.checkpoint:
                self.checkpoint()
            if time.monotonic() >= deadline:
                raise TimeoutError('Local model exceeded its total inference deadline')

        check()
        # One process owns the application worker. Lock waits remain cancellable.
        while not _inference_lock.acquire(timeout=.2):
            check()
        try:
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(connect=5, read=self.settings.model_timeout, write=10, pool=5)) as client:
                network_socket=[]
                def abort():
                    if network_socket:
                        try: network_socket[0].shutdown(socket.SHUT_RDWR)
                        except OSError: pass
                    client.close()
                timer=Timer(max(.01,deadline-time.monotonic()),abort); timer.daemon=True; timer.start()
                try:
                    response_context=client.stream('POST', 'http://127.0.0.1:11434/api/chat', json=payload)
                    with response_context as response:
                        stream=response.extensions.get('network_stream')
                        if stream and stream.get_extra_info('socket'):
                            network_socket.append(stream.get_extra_info('socket'))
                        return self._consume_stream(response,payload,message,started,check,tools)
                finally:
                    timer.cancel()
        finally:
            self.last_metrics['elapsed_seconds']=round(time.monotonic()-started,2)
            _inference_lock.release()

    def _consume_stream(self,response,payload,message,started,check,tools):
        received, done, last_notice, first_token = 0, False, 0, None
        try:
            response.raise_for_status()
            for line in response.iter_lines():
                check()
                received += len(line.encode('utf-8'))
                if received > 200_000 or len(line) > 100_000:
                    raise ValueError('Model stream exceeded output limit')
                if not line:
                    continue
                frame = json.loads(line)
                if frame.get('error'):
                    raise RuntimeError(str(frame['error'])[:250])
                delta = frame.get('message', {})
                message['content'] += delta.get('content') or ''
                if delta.get('tool_calls'):
                    message.setdefault('tool_calls', []).extend(delta['tool_calls'])
                if len(message['content']) > 30_000:
                    raise ValueError('Model content exceeded output limit')
                if delta.get('content') and first_token is None:
                    first_token = time.monotonic()-started
                elapsed = time.monotonic()-started
                if self.progress and elapsed-last_notice >= 3:
                    self.progress(f'Local model generating ({len(message["content"])} characters, {elapsed:.0f}s)')
                    last_notice=elapsed
                self.last_metrics = dict(elapsed_seconds=round(elapsed,2), first_token_seconds=first_token,
                    prompt_tokens=frame.get('prompt_eval_count'), generated_tokens=frame.get('eval_count'),
                    load_seconds=frame.get('load_duration',0)/1e9, generation_seconds=frame.get('eval_duration',0)/1e9,
                    early_json_stop=False)
                # JSON mode may generate trailing whitespace. Stop once
                # the whole response object is valid, never mid-object.
                if payload.get('format') and not tools:
                    try:
                        parsed=json.loads(message['content'])
                    except json.JSONDecodeError:
                        parsed=None
                    if isinstance(parsed,dict):
                        self.last_metrics['early_json_stop']=not frame.get('done',False)
                        done=True
                        break
                if frame.get('done'):
                    done=True
                    if frame.get('done_reason')=='length' and payload.get('format'):
                        raise ValueError('Structured model output exceeded its token budget')
                    break
        except Exception:
            check()
            raise
        if not done:
            raise RuntimeError('Local model stream ended without a completed response')
        check()
        return message

    def complete(self, system, prompt, tokens=500):
        message = self._chat(system, prompt, tokens)
        content = message.get('content', '').strip()
        if not content:
            raise RuntimeError('Local model returned empty content')
        return content

    def complete_json(self, system, prompt, output_model, tokens=240):
        message=self._chat(system,prompt,tokens,output_schema=output_model.model_json_schema())
        return output_model.model_validate_json(message['content']).model_dump()

    def select_plan(self, prompt):
        tool = dict(type='function', function=dict(name='plan_task', description='Plan a local NEXUS task using only available tools.', parameters=Plan.model_json_schema()))
        message = self._chat('Call plan_task once. Do not claim execution. Available formats: pdf,docx,xlsx,pptx,csv,txt,json. Browser can read public HTTPS pages only. No shell, email or purchases.', prompt, 220, [tool])
        calls = message.get('tool_calls', [])
        if len(calls) != 1 or calls[0].get('function', {}).get('name') != 'plan_task':
            raise ValueError('Model did not return one permitted tool call')
        args = calls[0]['function'].get('arguments', {})
        if isinstance(args, str):
            args = json.loads(args)
        return Plan.model_validate(args)

    def health(self):
        try:
            with httpx.Client(trust_env=False, timeout=3) as client:
                models = client.get('http://127.0.0.1:11434/api/tags').json()['models']
            return dict(reachable=True, installed=any(x['name'] == self.settings.model for x in models))
        except Exception:
            return dict(reachable=False, installed=False)

    def unload(self):
        """Release this model before an on-demand browser or under RAM pressure."""
        try:
            with _inference_lock, httpx.Client(trust_env=False, timeout=10) as client:
                response = client.post('http://127.0.0.1:11434/api/generate', json=dict(model=self.settings.model, keep_alive=0, stream=False))
                response.raise_for_status()
            return True
        except Exception:
            return False
