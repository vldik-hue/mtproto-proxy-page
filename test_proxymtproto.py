#!/usr/bin/env python3
from collections import defaultdict
from update_page import PROXYMT_LABEL, parse_proxymtproto_feed, verify

sample = r'''
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
    Server: <code>cdntide.org</code><br/>
    Port: <code>443</code><br/>
    Secret: <code>ddee10a29f2e8abc6797a0c9cb1d476c39</code>
  </div>
  <time datetime="2026-10-06T14:30:00+00:00"></time>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
    Server: <code>Unknown</code><br/>
    Port: <code>8443</code><br/>
    Secret: <code>eeNEgYdJvXrFGRMCIMJdCQ</code>
  </div>
  <time datetime="2026-10-06T15:00:00+00:00"></time>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
    Server: <code>akenai.tg</code><br/>
    Port: <code>853</code><br/>
    Secret: <code>ee54ce330e4690cc297d2b031ff3f288b06d742e616b656e61692e636c69636b</code>
  </div>
  <time datetime="2026-10-06T16:30:00+00:00"></time>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
    Server: <code>cdntide.org.</code><br/>
    Port: <code>443</code><br/>
    Secret: <code>ddee10a29f2e8abc6797a0c9cb1d476c39</code>
  </div>
  <time datetime="2026-10-06T17:30:00+00:00"></time>
</div>
'''

items = parse_proxymtproto_feed(sample)
assert len(items) == 2, items
assert [x["server"] for x in items] == ["cdntide.org", "akenai.tg"], items
assert items[0]["published_at"] == "2026-10-06T17:30:00+00:00"
assert items[0]["repeat_count"] == 2
assert items[0]["source"] == "@ProxyMTProto"
assert items[1]["port"] == 853

# Priority channel posts must not be removed or reordered by GitHub-side TCP probing.
bucket = defaultdict(list)
bucket[PROXYMT_LABEL] = items
verified = verify(bucket)
assert [x["server"] for x in verified[PROXYMT_LABEL]] == ["cdntide.org", "akenai.tg"], verified
assert all(x.get("channel_fresh") is True for x in verified[PROXYMT_LABEL]), verified

print("ProxyMTProto freshness path OK")
