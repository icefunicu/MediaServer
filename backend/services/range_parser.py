"""
HTTP Range 请求解析模块

提供 HTTP Range 请求头的解析功能，支持三种格式：
- bytes=start-end: 指定起始和结束字节
- bytes=start-: 从起始字节到文件末尾
- bytes=-suffix: 文件最后 suffix 个字节
"""

from typing import Tuple

from backend.logging_config import get_logger


logger = get_logger("range_parser")


class RangeParseError(ValueError):
    """Range 请求解析错误"""
    pass


def parse_range_header(range_header: str, file_size: int) -> Tuple[int, int]:
    """
    解析 HTTP Range 请求头

    Args:
        range_header: Range 请求头字符串（如 "bytes=0-1023"）
        file_size: 文件总大小（字节）

    Returns:
        元组 (start, end)，包含起始和结束字节位置

    Raises:
        RangeParseError: Range 请求头格式无效或超出范围

    Examples:
        >>> parse_range_header("bytes=0-1023", 2048)
        (0, 1023)
        >>> parse_range_header("bytes=1024-", 2048)
        (1024, 2047)
        >>> parse_range_header("bytes=-1024", 2048)
        (1024, 2047)
    """
    if not range_header:
        raise RangeParseError("Range 请求头为空")

    if not range_header.startswith("bytes="):
        raise RangeParseError("无效的 Range 请求头格式：必须以 'bytes=' 开头")

    range_str = range_header[6:]  # 移除 "bytes=" 前缀

    if "-" not in range_str:
        raise RangeParseError("Range 请求头缺少分隔符 '-'")

    parts = range_str.split("-", 1)
    start_str = parts[0].strip()
    end_str = parts[1].strip()

    if file_size <= 0:
        raise RangeParseError(f"无效的文件大小: {file_size}")

    try:
        if start_str == "":
            # 格式：bytes=-1024（最后1024字节）
            suffix_length = int(end_str)
            if suffix_length < 0:
                raise RangeParseError("后缀长度不能为负数")
            start = max(0, file_size - suffix_length)
            end = file_size - 1
        elif end_str == "":
            # 格式：bytes=1024-（从1024到文件末尾）
            start = int(start_str)
            if start < 0:
                raise RangeParseError("起始位置不能为负数")
            end = file_size - 1
        else:
            # 格式：bytes=1024-2047（指定范围）
            start = int(start_str)
            end = int(end_str)

    except ValueError as e:
        raise RangeParseError(f"Range 请求头包含无效数字: {e}")

    if start < 0:
        raise RangeParseError(f"起始位置不能为负数: {start}")

    if start > end:
        raise RangeParseError(f"起始位置大于结束位置: {start} > {end}")

    if start >= file_size:
        raise RangeParseError(
            f"起始位置超出文件范围: {start} >= {file_size}"
        )

    if end >= file_size:
        end = file_size - 1

    return (start, end)


def build_content_range(start: int, end: int, file_size: int) -> str:
    """
    构建 Content-Range 响应头

    Args:
        start: 起始字节位置
        end: 结束字节位置
        file_size: 文件总大小

    Returns:
        Content-Range 头字符串（如 "bytes 0-1023/2048"）
    """
    return f"bytes {start}-{end}/{file_size}"


def build_range_response_headers(
    start: int,
    end: int,
    file_size: int,
    content_length: int
) -> dict:
    """
    构建 Range 响应头字典

    Args:
        start: 起始字节位置
        end: 结束字节位置
        file_size: 文件总大小
        content_length: 内容长度

    Returns:
        响应头字典
    """
    return {
        "Content-Range": build_content_range(start, end, file_size),
        "Accept-Ranges": "bytes",
        "Content-Length": str(content_length)
    }
