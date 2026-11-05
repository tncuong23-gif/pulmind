/** Prepare the same Markdown content shown in the chat for spoken playback. */
export function chatSpeech(markdown: string): string {
  let omittedTable = false;
  let omittedCode = false;
  let fence = "";
  const prose: string[] = [];
  for (const line of markdown.split("\n")) {
    const marker = line.match(/^\s{0,3}(`{3,}|~{3,})/)?.[1];
    if (fence) {
      if (marker?.[0] === fence[0] && marker.length >= fence.length) fence = "";
      continue;
    }
    if (marker) {
      fence = marker;
      omittedCode = true;
      continue;
    }
    if ((line.match(/(?<!\\)\|/g)?.length ?? 0) >= 2 || /^\s*\|/.test(line)) {
      omittedTable = true;
      continue;
    }
    const text = line
      .replace(/^\s{0,3}#{1,6}\s+/, "")
      .replace(/^\s*(?:>\s*)+/, "")
      .replace(/^\s*[-+*]\s+/, "")
      .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/<?https?:\/\/[^\s>]+>?/g, "")
      .replace(/(\*\*|__|`)(.+?)\1/g, "$2")
      .replace(/\[\s*\d+(?:\s*,\s*\d+)*\s*\]/g, "")
      .replace(/ {2,}/g, " ")
      .replace(/\s+([,.;:!?])/g, "$1")
      .trim();
    if (text) prose.push(/[.!?…:]$/.test(text) ? text : text + ".");
  }
  if (omittedTable) prose.push("Bạn có thể xem bảng chi tiết trong khung chat.");
  if (omittedCode) prose.push("Nội dung định dạng sẵn được hiển thị trong khung chat.");
  return prose.join(" ");
}
