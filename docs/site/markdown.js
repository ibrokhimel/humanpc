/* Minimal Markdown -> HTML renderer for the humanpc docs.
 * Supports the subset used by the docs: ATX headings, fenced code blocks,
 * GFM pipe tables, ordered/unordered lists, blockquotes, horizontal rules,
 * and inline code/bold/italic/links. Returns { html, headings }.
 */
(function (global) {
  "use strict";

  function esc(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function escAttr(s) {
    return esc(s).replace(/"/g, "&quot;");
  }
  function slugify(s) {
    return s.toLowerCase().replace(/`/g, "").replace(/[^\w]+/g, "-").replace(/^-+|-+$/g, "");
  }

  // Bold/italic on already-escaped text that contains no code spans or links.
  function emph(t) {
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
    t = t.replace(/\b_([^_\n]+)_\b/g, "<em>$1</em>");
    return t;
  }
  // Render a run that may hold inline code + bold/italic (but no links).
  function codeEmph(raw) {
    return raw.split(/(`[^`]+`)/g).map(function (p) {
      if (p.length > 1 && p[0] === "`" && p[p.length - 1] === "`")
        return "<code>" + esc(p.slice(1, -1)) + "</code>";
      return emph(esc(p));
    }).join("");
  }
  // Inline: single pass over code spans and links so a link's text may itself
  // contain inline code (e.g. [`docs/plan.md`](docs/plan.md)). Code spans are
  // opaque, so link syntax inside a code span is left alone.
  function inline(s) {
    var re = /(`[^`]+`)|(\[[^\]]+\]\([^)]*\))/g, out = "", last = 0, m;
    while ((m = re.exec(s))) {
      out += codeEmph(s.slice(last, m.index));
      if (m[1]) {
        out += "<code>" + esc(m[1].slice(1, -1)) + "</code>";
      } else {
        var lm = /^\[([^\]]+)\]\(([^)]*)\)$/.exec(m[2]);
        out += '<a href="' + escAttr(lm[2]) + '">' + codeEmph(lm[1]) + "</a>";
      }
      last = re.lastIndex;
    }
    return out + codeEmph(s.slice(last));
  }

  function splitRow(line) {
    var s = line.trim().replace(/^\|/, "").replace(/\|$/, "");
    return s.split("|").map(function (c) { return c.trim(); });
  }

  function isBlockStart(line) {
    return /^```/.test(line) || /^#{1,6}\s/.test(line) || /^\s*[-*+]\s+/.test(line) ||
      /^\s*\d+\.\s+/.test(line) || /^>\s?/.test(line) || /^(-{3,}|\*{3,}|_{3,})\s*$/.test(line);
  }

  function render(src) {
    var lines = src.replace(/\r\n/g, "\n").split("\n");
    var html = "", headings = [], i = 0;

    while (i < lines.length) {
      var line = lines[i];

      // Fenced code block.
      if (/^```/.test(line.trim())) {
        var lang = line.trim().slice(3).trim() || "text";
        i++;
        var buf = [];
        while (i < lines.length && !/^```/.test(lines[i].trim())) { buf.push(lines[i]); i++; }
        i++; // closing fence
        html += '<div class="code"><div class="code-head"><span class="lang">' + esc(lang) +
          '</span><button class="copy" type="button">Copy</button></div><pre><code class="language-' +
          esc(lang) + '">' + esc(buf.join("\n")) + "</code></pre></div>";
        continue;
      }

      if (line.trim() === "") { i++; continue; }

      // Heading.
      var h = /^(#{1,6})\s+(.*)$/.exec(line);
      if (h) {
        var lvl = h[1].length, text = h[2].trim(), slug = slugify(text);
        if (lvl >= 1 && lvl <= 3) headings.push({ level: lvl, text: text, slug: slug });
        html += "<h" + lvl + ' id="' + slug + '"><a class="anchor" href="#' + slug + '">#</a>' +
          inline(text) + "</h" + lvl + ">";
        i++; continue;
      }

      // Horizontal rule.
      if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line.trim())) { html += "<hr>"; i++; continue; }

      // Blockquote (consecutive `>` lines, rendered recursively).
      if (/^>\s?/.test(line)) {
        var q = [];
        while (i < lines.length && /^>\s?/.test(lines[i])) { q.push(lines[i].replace(/^>\s?/, "")); i++; }
        html += "<blockquote>" + render(q.join("\n")).html + "</blockquote>";
        continue;
      }

      // GFM table: a row with '|' followed by a separator row of dashes.
      if (line.indexOf("|") !== -1 && i + 1 < lines.length &&
          /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/.test(lines[i + 1]) && lines[i + 1].indexOf("-") !== -1) {
        var header = splitRow(line);
        i += 2;
        var rows = [];
        while (i < lines.length && lines[i].indexOf("|") !== -1 && lines[i].trim() !== "") {
          rows.push(splitRow(lines[i])); i++;
        }
        var t = '<div class="table-wrap"><table><thead><tr>';
        header.forEach(function (c) { t += "<th>" + inline(c) + "</th>"; });
        t += "</tr></thead><tbody>";
        rows.forEach(function (r) {
          t += "<tr>";
          for (var c = 0; c < header.length; c++) t += "<td>" + inline(r[c] || "") + "</td>";
          t += "</tr>";
        });
        html += t + "</tbody></table></div>";
        continue;
      }

      // Unordered list.
      if (/^\s*[-*+]\s+/.test(line)) {
        var items = [];
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*[-*+]\s+/, "")); i++;
        }
        html += "<ul>" + items.map(function (li) { return "<li>" + inline(li) + "</li>"; }).join("") + "</ul>";
        continue;
      }

      // Ordered list.
      if (/^\s*\d+\.\s+/.test(line)) {
        var oitems = [];
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          oitems.push(lines[i].replace(/^\s*\d+\.\s+/, "")); i++;
        }
        html += "<ol>" + oitems.map(function (li) { return "<li>" + inline(li) + "</li>"; }).join("") + "</ol>";
        continue;
      }

      // Paragraph: gather until a blank line or a new block.
      var para = [line]; i++;
      while (i < lines.length && lines[i].trim() !== "" && !isBlockStart(lines[i])) { para.push(lines[i]); i++; }
      html += "<p>" + inline(para.join(" ")) + "</p>";
    }

    return { html: html, headings: headings };
  }

  global.renderMarkdown = render;
})(window);
