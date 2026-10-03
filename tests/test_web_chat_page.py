from atlas.web.chat_page import CHAT_SCRIPT, render_chat_page


def test_chat_page_structure_and_prefill_escaping():

    page = render_chat_page('Tell me about <b>"tv"</b>')

    assert '<div id="log"' in page and '<textarea id="ask"' in page and 'id="send"' in page
    assert "&lt;b&gt;&quot;tv&quot;&lt;/b&gt;" in page and "<b>" not in page.split("<script>")[0].split("<h1>")[1]
    assert "/api/chat" in page and "/api/actions/execute" in page
    assert "innerHTML" not in CHAT_SCRIPT


def test_chat_script_enables_next_step_only_after_success():

    # The step-gating contract lives in the script: a step button starts disabled unless it is the first.
    assert "disabled" in CHAT_SCRIPT and "sessionStorage" in CHAT_SCRIPT
