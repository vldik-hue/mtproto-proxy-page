#!/usr/bin/env python3
from update_page import parse_proxymtproto_feed

sample = r'''
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
    Server: <code>cdntide.org</code><br/>
    Port: <code>443</code><br/>
    Secret: <code>ddee10a29f2e8abc6797a0c9cb1d476c39</code><br/>
    @ProxyMTProto
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
    Server: <code>cdntide.org.</code><br/>
    Port: <code>443</code><br/>
    Secret: <code>ddee10a29f2e8abc6797a0c9cb1d476c39</code>
  </div>
  <time datetime="2026-10-06T17:30:00+00:00"></time>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
  <div class="tgme_widget_message_text js-message_text" dir="auto">
    Server: <code>akenai.tg</code><br/>
    Port: <code>853</code><br/>
    Secret: <code>ee54ce330e4690cc297d2b031ff3f288b06d742e616b656e61692e636c69636b</code>
  </div>
  <time datetime="2026-10-06T12:30:00+00:00"></time>
</div>
'''

items = parse_proxymtproto_feed(sample)
assert len(items) == 2, items
by_server = {x["server"]: x for x in items}
assert "Unknown" not in by_server
assert by_server["cdntide.org"]["repeat_count"] == 2
assert by_server["cdntide.org"]["published_at"] == "2026-10-06T17:30:00+00:00"
assert by_server["cdntide.org"]["source"] == "@ProxyMTProto"
assert by_server["akenai.tg"]["port"] == 853
assert by_server["akenai.tg"]["priority"] is True
print("ProxyMTProto parser OK")
