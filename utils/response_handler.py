import discord


def split_message(msg: str) -> list[str, ...]:
    """Split a message into multiple messages if it exceeds the Discord message limit."""
    DISCORD_MESSAGE_LIMIT = 2000
    if len(msg) <= DISCORD_MESSAGE_LIMIT:
        return [msg]

    messages = []
    while len(msg) > DISCORD_MESSAGE_LIMIT:
        split_index = max(msg[:DISCORD_MESSAGE_LIMIT].rfind("."), msg[:DISCORD_MESSAGE_LIMIT].rfind(":"), msg[:DISCORD_MESSAGE_LIMIT].rfind("!"), msg[:DISCORD_MESSAGE_LIMIT].rfind("?"))
        if split_index == -1:
            split_index = DISCORD_MESSAGE_LIMIT

        messages.append(msg[:split_index + 1].strip())
        msg = msg[split_index + 1:].strip()

    messages.append(msg)
    return messages


def check_attachment_errors(attachments: list[discord.File | None, ...]) -> tuple[list[discord.File, ...], bool]:
    """Check if the attachments are valid and return a list of valid attachments."""
    return [attachment for attachment in attachments if attachment is not None], True if any(attachment is None for attachment in attachments) else False


async def check_reference_needed(message: discord.message.Message) -> bool:
    """Check if a reference is needed for the response due to other messages being sent in the channel."""
    async for msg in message.channel.history(limit=1):
        return True if msg.id != message.id else False


async def send_response(message: discord.message.Message, response: str, attachments: list[discord.File | None, ...] = []):
    """Send the response messages in the channel with reference and attachments if needed."""
    split_responses = split_message(response)
    attachments, attachment_error = check_attachment_errors(attachments)
    for i, split_response in enumerate(split_responses):
        if i == 0 and await check_reference_needed(message):
            if attachments and i == len(split_responses) - 1:
                await message.channel.send(content=split_response, reference=message, files=attachments[:10])
            else:
                await message.channel.send(content=split_response, reference=message)
        else:
            if attachments and i == len(split_responses) - 1:
                await message.channel.send(content=split_response, files=attachments[:10])
            else:
                await message.channel.send(content=split_response)

    if attachments:
        if len(attachments) > 10:
            for i in range(10, len(attachments), 10):
                await message.channel.send(files=attachments[i:i + 10])
        
        if attachment_error:
            await message.channel.send(content="**Note:** At least one image could not be generated, sorry about that.")
