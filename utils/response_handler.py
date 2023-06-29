import discord


class ResponseHandler:
    DISCORD_MESSAGE_LIMIT = 2000

    def __init__(self, message: discord.message.Message):
        self.message = message

    def split_message(self, msg: str) -> list[str]:
        """Split a message into multiple messages if it exceeds the Discord message limit."""
        if len(msg) <= self.DISCORD_MESSAGE_LIMIT:
            return [msg]

        messages = []
        while len(msg) > self.DISCORD_MESSAGE_LIMIT:
            split_index = max(msg[:self.DISCORD_MESSAGE_LIMIT].rfind("."), msg[:self.DISCORD_MESSAGE_LIMIT].rfind(":"), msg[:self.DISCORD_MESSAGE_LIMIT].rfind("!"), msg[:self.DISCORD_MESSAGE_LIMIT].rfind("?"))
            if split_index == -1:
                split_index = self.DISCORD_MESSAGE_LIMIT

            messages.append(msg[:split_index + 1].strip())
            msg = msg[split_index + 1:].strip()

        messages.append(msg)
        return messages

    async def check_reference_needed(self) -> bool:
        """Check if a reference is needed for the response due to other messages being sent in the channel."""
        async for msg in self.message.channel.history(limit=1):
            return True if msg.id != self.message.id else False

    async def send_response(self, response: str, attachments: list[discord.File | None, ...] = []):
        """Send the response messages in the channel with reference and attachments if needed."""
        split_responses = self.split_message(response)
        attachments = [attachment for attachment in attachments if attachment is not None]

        for i, split_response in enumerate(split_responses):
            if i == 0 and await self.check_reference_needed():
                if attachments and i == len(split_responses) - 1:
                    await self.message.channel.send(content=split_response, reference=self.message, files=attachments[:10])
                else:
                    await self.message.channel.send(content=split_response, reference=self.message)
            else:
                if attachments and i == len(split_responses) - 1:
                    await self.message.channel.send(content=split_response, files=attachments[:10])
                else:
                    await self.message.channel.send(content=split_response)

        if attachments:
            if len(attachments) > 10:
                for i in range(10, len(attachments), 10):
                    await self.message.channel.send(files=attachments[i:i + 10])
                    