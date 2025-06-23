import asyncio
import json
import logging
import os
import sys

import arc
import hikari
import httpx
import validators

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

bot = hikari.GatewayBot(os.environ["TOKEN"])
arc_client = arc.GatewayClient(bot)
httpx_client = httpx.AsyncClient(timeout=15.0)
logger: logging.Logger = logging.getLogger("PingCat")

hosts = [
    "Amsterdam, Netherlands - AS214677 Matteo Martelloni trading as DELUXHOST.",
    "Taichung, Taiwan - AS17809 VEE TIME CORP.",
    "Kaohsiung, Taiwan - AS3462 HiNet (Chunghwa Telecom).",
    "Los Angeles, United States - AS36352 HostPapa.",
]


async def identify_ip(ip_address: str):
    """Identify the type of target (IPv4, IPv6, domain, or private IP)"""
    if validators.ip_address._check_private_ip(ip_address, is_private=True):
        return "private", ip_address

    if validators.ipv4(ip_address):
        return "ipv4", ip_address

    if validators.ipv6(ip_address):
        return "ipv6", ip_address

    if validators.domain(ip_address):
        # Since pingserver now supports domain names directly,
        # we don't need to resolve them anymore
        return "domain", ip_address

    return "invalid", ip_address


async def ping_host(
    ctx: arc.GatewayContext,
    url: str,
    api_key: str,
    target: str,
    target_type: str,
    host: str,
    private: bool,
) -> arc.InteractionResponse:
    data = {
        "target": target,  # This is actually a domain name now
        "ip_version": "auto",
        "api_key": api_key,
    }

    # Log the URL being used for debugging (hide if private)
    log_url = "[HIDDEN]" if private else url
    logger.info(f"Attempting ping from {host} using URL: {log_url}")
    logger.debug(f"Request data: {data}")
    
    # Basic URL validation
    if not url or not url.startswith(("http://", "https://")):
        logger.error(f"Invalid URL for {host}: {url}")
        return await ctx.respond(f"Configuration error: Invalid URL for {host}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(url, json=data)
            response.raise_for_status()
            json_response = response.json()
        except httpx.TimeoutException:
            # `::` always timeout for some reason, shouldn't it return non-success?
            logger.error(f"Timeout occurred for URL: {log_url}")
            return await ctx.respond(
                "Error: Timeout while attempting to ping the target. Please check if the entered address is correct.",
            )
        except httpx.HTTPStatusError as e:
            # HTTPStatusError means we got a response, so response should be available
            logger.error(f"HTTP error {e.response.status_code} for URL: {log_url}")
            logger.exception(e)
            
            # Try to parse JSON response, but handle cases where it's not valid JSON
            try:
                json_response = response.json()
                result = json_response.get("output", f"Server returned HTTP {e.response.status_code}")
            except (ValueError, json.JSONDecodeError):
                # Response is not valid JSON
                result = f"Server returned HTTP {e.response.status_code}. Response: {response.text[:200]}"
            
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)
        except httpx.ConnectError as e:
            # DNS/connection errors
            logger.error(f"Connection failed for URL: {log_url} - {str(e)}")
            if "nodename nor servname provided" in str(e) or "Name or service not known" in str(e):
                result = f"Error: Cannot resolve hostname for {host}. The ping server may be temporarily unavailable."
            else:
                result = f"Error: Cannot connect to {host}. The ping server may be temporarily unavailable."
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)
        except httpx.RequestError as e:
            # Other request errors
            logger.error(f"Request error for URL: {log_url} - {str(e)}")
            logger.exception(e)
            result = f"Error: Request failed for {host}. Please try again later."
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)
        except Exception as e:
            # Other errors - handle without assuming response exists
            logger.error(f"Unexpected error for URL: {log_url} - {str(e)}")
            logger.exception(e)
            result = "An unexpected error occurred while attempting to ping the target."
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)

        logger.info(
            f"{'=' * 30}\nStatus Code: {response.status_code}\nResponse Content: {response.json()}\n{'=' * 30}\n",
        )

        if json_response.get("success"):
            formatted_response = (
                f"Ping result from `{host}`\n```\n{json_response.get('output')}\n```"
            ).replace(url, "[HIDDEN]")
            return await ctx.respond(formatted_response)

        return await ctx.respond(json_response.get("output", "Unknown error occurred."))


async def mtr_host(
    ctx: arc.GatewayContext,
    url: str,
    api_key: str,
    target: str,
    target_type: str,
    host: str,
    private: bool,
) -> arc.InteractionResponse:
    data = {
        "target": target,
        "ip_version": "auto",
        "api_key": api_key,
    }

    # Log the URL being used for debugging (hide if private)
    log_url = "[HIDDEN]" if private else url
    logger.info(f"Attempting MTR from {host} using URL: {log_url}")
    logger.debug(f"Request data: {data}")
    
    # Basic URL validation
    if not url or not url.startswith(("http://", "https://")):
        logger.error(f"Invalid URL for {host}: {url}")
        return await ctx.respond(f"Configuration error: Invalid URL for {host}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, json=data)
            response.raise_for_status()
            json_response = response.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout occurred for MTR URL: {log_url}")
            return await ctx.respond(
                "Error: Timeout while attempting to run MTR to the target. Please check if the entered address is correct.",
            )
        except httpx.HTTPStatusError as e:
            # HTTPStatusError means we got a response, so response should be available
            logger.error(f"HTTP error {e.response.status_code} for MTR URL: {log_url}")
            logger.exception(e)
            
            # Try to parse JSON response, but handle cases where it's not valid JSON
            try:
                json_response = response.json()
                result = json_response.get("output", f"Server returned HTTP {e.response.status_code}")
            except (ValueError, json.JSONDecodeError):
                # Response is not valid JSON
                result = f"Server returned HTTP {e.response.status_code}. Response: {response.text[:200]}"
            
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)
        except httpx.ConnectError as e:
            # DNS/connection errors
            logger.error(f"Connection failed for MTR URL: {log_url} - {str(e)}")
            if "nodename nor servname provided" in str(e) or "Name or service not known" in str(e):
                result = f"Error: Cannot resolve hostname for {host}. The MTR server may be temporarily unavailable."
            else:
                result = f"Error: Cannot connect to {host}. The MTR server may be temporarily unavailable."
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)
        except httpx.RequestError as e:
            # Other request errors
            logger.error(f"Request error for MTR URL: {log_url} - {str(e)}")
            logger.exception(e)
            result = f"Error: Request failed for {host}. Please try again later."
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)
        except Exception as e:
            # Other errors - handle without assuming response exists
            logger.error(f"Unexpected error for MTR URL: {log_url} - {str(e)}")
            logger.exception(e)
            result = "An unexpected error occurred while attempting to run MTR to the target."
            if private:
                result = result.replace(url, "[HIDDEN]")
            return await ctx.respond(result)

        logger.info(
            f"{'=' * 30}\nStatus Code: {response.status_code}\nResponse Content: {response.json()}\n{'=' * 30}\n",
        )

        if json_response.get("success"):
            formatted_response = (
                f"MTR result from `{host}`\n```\n{json_response.get('output')}\n```"
            ).replace(url, "[HIDDEN]")
            return await ctx.respond(formatted_response)

        return await ctx.respond(json_response.get("output", "Unknown error occurred."))


def get_host_info():
    """Get host configuration for both ping and MTR endpoints"""
    host_config = {
        "Tainan, Taiwan - AS3462 HiNet (Chunghwa Telecom).": {
            "ping_url": "http://ryanisyyds.asuscomm.com:9199/ping",
            "mtr_url": "http://ryanisyyds.asuscomm.com:9199/mtr",
            "api_key": os.environ.get("APIKEY3", ""),
            "private": True,
        },
        "Amsterdam, Netherlands - AS214677 Matteo Martelloni trading as DELUXHOST.": {
            "ping_url": os.environ.get("IP1", ""),
            "mtr_url": os.environ.get("IP1", "").replace("/ping", "/mtr") if os.environ.get("IP1") else "",
            "api_key": os.environ.get("APIKEY1", ""),
            "private": True,
        },
        "Kaohsiung, Taiwan - AS3462 HiNet (Chunghwa Telecom).": {
            "ping_url": os.environ.get("IP2", ""),
            "mtr_url": os.environ.get("IP2", "").replace("/ping", "/mtr") if os.environ.get("IP2") else "",
            "api_key": os.environ.get("APIKEY2", ""),
            "private": True,
        },
        "Taichung, Taiwan - AS17809 VEE TIME CORP.": {
            "ping_url": "http://cowgl.xyz:9199/ping",
            "mtr_url": "http://cowgl.xyz:9199/mtr",
            "api_key": os.environ.get("APIKEY0", ""),
            "private": True,
        },
        "Los Angeles, United States - AS36352 HostPapa.": {
            "ping_url": "http://lax1.maoyue.tw:9199/ping",
            "mtr_url": "http://lax1.maoyue.tw:9199/mtr",
            "api_key": "",
            "private": False,
        },
    }
    
    # Validate URLs
    for host, config in host_config.items():
        ping_url = config["ping_url"]
        mtr_url = config["mtr_url"]
        
        if not ping_url:
            logger.warning(f"Missing ping URL for {host}")
        elif not ping_url.startswith(("http://", "https://")):
            logger.warning(f"Invalid ping URL format for {host}: {ping_url}")
            
        if not mtr_url:
            logger.warning(f"Missing MTR URL for {host}")
        elif not mtr_url.startswith(("http://", "https://")):
            logger.warning(f"Invalid MTR URL format for {host}: {mtr_url}")
    
    return host_config


async def validate_endpoints():
    """Validate that all endpoints are reachable at startup"""
    host_info = get_host_info()
    logger.info("Validating endpoints...")
    
    for host, config in host_info.items():
        ping_url = config["ping_url"]
        mtr_url = config["mtr_url"]
        is_private = config["private"]
        
        log_ping_url = "[HIDDEN]" if is_private else ping_url
        log_mtr_url = "[HIDDEN]" if is_private else mtr_url
        
        # Test ping endpoint
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Just do a basic connectivity test, don't send actual ping data
                response = await client.get(ping_url.replace("/ping", "/") if "/ping" in ping_url else ping_url, 
                                          follow_redirects=True)
                logger.info(f"✓ Ping endpoint reachable for {host}: {log_ping_url}")
        except Exception as e:
            logger.warning(f"✗ Ping endpoint unreachable for {host}: {log_ping_url} - {str(e)}")
        
        # Test MTR endpoint
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Just do a basic connectivity test, don't send actual MTR data
                response = await client.get(mtr_url.replace("/mtr", "/") if "/mtr" in mtr_url else mtr_url,
                                          follow_redirects=True)
                logger.info(f"✓ MTR endpoint reachable for {host}: {log_mtr_url}")
        except Exception as e:
            logger.warning(f"✗ MTR endpoint unreachable for {host}: {log_mtr_url} - {str(e)}")
    
    logger.info("Endpoint validation complete.")


@arc_client.include
@arc.slash_command("ping", "Ping test!")
async def handle_ping_command(
    ctx: arc.GatewayContext,
    target: arc.Option[str, arc.StrParams("Which IP or domain do you want to ping?")],
    host: arc.Option[
        str,
        arc.StrParams(
            "Which host do you want to ping from?",
            choices=hosts,
        ),
    ],
) -> arc.InteractionResponse:
    target_type, detected_target = await identify_ip(target)

    if target_type == "invalid":
        return await ctx.respond("Invalid IP address or domain name.")

    if target_type == "private":
        return await ctx.respond("Private IP addresses are not allowed.")

    host_info = get_host_info()

    if host not in host_info:
        return await ctx.respond("Host not supported yet.")

    url = host_info[host]["ping_url"]
    api_key = host_info[host]["api_key"]
    is_private = host_info[host]["private"]

    return await ping_host(
        ctx, url, api_key, detected_target, target_type, host, is_private
    )


@arc_client.include
@arc.slash_command("mtr", "MTR (My Traceroute) test!")
async def handle_mtr_command(
    ctx: arc.GatewayContext,
    target: arc.Option[
        str, arc.StrParams("Which IP or domain do you want to trace to?")
    ],
    host: arc.Option[
        str,
        arc.StrParams(
            "Which host do you want to run MTR from?",
            choices=hosts,
        ),
    ],
) -> arc.InteractionResponse:
    target_type, detected_target = await identify_ip(target)

    if target_type == "invalid":
        return await ctx.respond("Invalid IP address or domain name.")

    if target_type == "private":
        return await ctx.respond("Private IP addresses are not allowed.")

    host_info = get_host_info()

    if host not in host_info:
        return await ctx.respond("Host not supported yet.")

    url = host_info[host]["mtr_url"]
    api_key = host_info[host]["api_key"]
    is_private = host_info[host]["private"]

    return await mtr_host(
        ctx, url, api_key, detected_target, target_type, host, is_private
    )


# Validate endpoints when the bot starts
@bot.listen()
async def on_starting(event: hikari.StartingEvent) -> None:
    """Run endpoint validation when bot is starting"""
    await validate_endpoints()


# Start the bot
if __name__ == "__main__":
    bot.run()
