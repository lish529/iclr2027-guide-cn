#!/usr/bin/env python3
"""Interactive official OpenReview API login; credentials stay in this process only."""
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from types import SimpleNamespace
from pipeline import fetch

def post(endpoint, body):
    request = urllib.request.Request('https://api2.openreview.net/' + endpoint,
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
        'Accept': 'application/json', 'User-Agent': 'ICLR2027-Guide-CN/0.1'})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'OpenReview 登录请求失败（HTTP {e.code}），请检查账号或使用官方登录流程。') from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError('OpenReview 登录网络请求失败。') from None

def main():
    if not sys.stdin.isatty():
        raise SystemExit('请在本地交互终端运行，避免在命令行参数或日志中暴露凭据。')
    print('此命令仅向 https://api2.openreview.net 的官方登录接口提交凭据。')
    print('账号、密码、验证码不回显；token 只在当前进程使用，不保存到文件。')
    username = getpass.getpass('OpenReview 邮箱（不回显）: ')
    password = getpass.getpass('OpenReview 密码（不回显）: ')
    try:
        result = post('login', {'id': username, 'password': password, 'expiresIn': 3600})
    finally:
        username = password = ''
    if result.get('mfaPending'):
        methods = result.get('mfaMethods', [])
        method = 'totp' if 'totp' in methods else ('emailOtp' if 'emailOtp' in methods else None)
        if not method:
            raise RuntimeError('该账号需要通行密钥，请通过 OpenReview 官方客户端完成登录。')
        pending = result['mfaPendingToken']
        if method == 'emailOtp':
            post('mfa/challenge', {'mfaPendingToken': pending, 'method': method})
        code = getpass.getpass('OpenReview 双重验证代码（不回显）: ')
        result = post('mfa/verify', {'mfaPendingToken': pending, 'method': method, 'code': code})
        code = pending = ''
    token = result.get('token')
    result = {}
    if not token:
        raise RuntimeError('登录没有返回会话授权；未进行任何采集。')
    previous = os.environ.get('OPENREVIEW_TOKEN')
    os.environ['OPENREVIEW_TOKEN'] = token
    token = ''
    print('登录成功，开始只读采集公开投稿元数据。')
    try:
        fetch(SimpleNamespace(new=False))
    finally:
        if previous is None:
            os.environ.pop('OPENREVIEW_TOKEN', None)
        else:
            os.environ['OPENREVIEW_TOKEN'] = previous

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, KeyboardInterrupt, EOFError) as e:
        print(str(e) if isinstance(e, RuntimeError) else '已取消；凭据未保存。', file=sys.stderr)
        sys.exit(1)
