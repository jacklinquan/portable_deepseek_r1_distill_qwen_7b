"""Llama Chatbot

- Author: Quan Lin
- License: MIT
"""

from queue import Queue
from threading import Thread, Event
import asyncio

from llama_cpp import Llama


class ConsoleChatBot:
    def __init__(self, model: Llama, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt

    def run(self):
        messages = [{"role": "system", "content": self.system_prompt}]

        while True:
            prompt = input("User:\n")
            messages.append({"role": "user", "content": prompt})
            print("Assistant:")

            while True:
                # As `messages` grows, the requested tokens could exceed context window.
                # To deal with the raised ValueError, delete half of the history messages.
                # And continue trying until it fits context window.
                try:
                    response = self.model.create_chat_completion(
                        messages=messages,
                        stream=True,
                    )
                    response_message = {}
                    content_list = []
                    for chunk in response:
                        delta_role = chunk["choices"][0]["delta"].get("role")
                        delta_content = chunk["choices"][0]["delta"].get("content")
                        if delta_role:
                            response_message["role"] = delta_role
                        if delta_content:
                            content_list.append(delta_content)
                            print(delta_content, end="", flush=True)
                    response_message["content"] = "".join(content_list)
                    messages.append(response_message)
                    print()

                    break
                except ValueError as ex:
                    if len(messages) <= 2:
                        # There is at most 1 user message.
                        raise ex
                    # Delete half of the history messages, and always keep the system message.
                    del messages[1 : len(messages) // 2 + 1]
                    print("(Half of the history messages deleted.)")


class ThreadChatBot:
    def __init__(self, model: Llama, system_prompt: str) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.prompt_queue = Queue()
        self.token_queue = Queue()
        self.stop_event = Event()
        self.chat_session_thread = Thread(target=self._chat_session_thread_target)
        self.chat_session_thread.start()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        self.stop_chat()

    def _chat_session_thread_target(self):
        messages = [{"role": "system", "content": self.system_prompt}]

        # print("Chat session started.")
        while True:
            if self.stop_event.is_set():
                # print("Chat session finished.")
                return

            if not self.prompt_queue.empty():
                prompt = self.prompt_queue.get()
                messages.append({"role": "user", "content": prompt})

                while True:
                    # As `messages` grows, the requested tokens could exceed context window.
                    # To deal with the raised ValueError, delete half of the history messages.
                    # And continue trying until it fits context window.
                    try:
                        response = self.model.create_chat_completion(
                            messages=messages,
                            stream=True,
                        )
                        response_message = {}
                        content_list = []
                        for chunk in response:
                            if self.stop_event.is_set():
                                # print("Chat session finished.")
                                return
                            delta_role = chunk["choices"][0]["delta"].get("role")
                            delta_content = chunk["choices"][0]["delta"].get("content")
                            if delta_role:
                                response_message["role"] = delta_role
                            if delta_content:
                                content_list.append(delta_content)
                                self.token_queue.put(delta_content)
                        response_message["content"] = "".join(content_list)
                        messages.append(response_message)
                        # A token of None represents the end of the answer
                        self.token_queue.put(None)
                        break
                    except ValueError as ex:
                        if len(messages) <= 2:
                            # There is at most 1 user message.
                            raise ex
                        # Delete half of the history messages, and always keep the system message.
                        del messages[1 : len(messages) // 2 + 1]

    def stop_chat(self):
        self.stop_event.set()

    def set_prompt(self, prompt: str):
        self.prompt_queue.put(prompt)

    def get_token(self) -> str | bool | None:
        if not self.token_queue.empty():
            return self.token_queue.get()
        # False means no token arrived yet
        return False


class AsyncThreadChatBot(ThreadChatBot):
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        self.stop_chat()

    async def async_get_token(self):
        while True:
            if not self.token_queue.empty():
                return self.token_queue.get()
            await asyncio.sleep(0)


def run_console_chatbot(model: Llama, system_prompt: str):
    chatbot = ConsoleChatBot(model, system_prompt)
    chatbot.run()


def run_thread_chatbot_in_console(model: Llama, system_prompt: str):
    with ThreadChatBot(model, system_prompt) as chatbot:
        while True:
            prompt = input("User:\n")
            chatbot.set_prompt(prompt)
            print("Assistant:")
            while True:
                token = chatbot.get_token()
                if token is None:
                    break
                elif token is False:
                    pass
                else:
                    print(token, end="", flush=True)
            print()


async def run_async_thread_chatbot_in_console(model: Llama, system_prompt: str):
    async with AsyncThreadChatBot(model, system_prompt) as chatbot:
        while True:
            prompt = input("User:\n")
            chatbot.set_prompt(prompt)
            print("Assistant:")
            while True:
                token = await chatbot.async_get_token()
                if token is None:
                    break
                else:
                    print(token, end="", flush=True)
            print()
