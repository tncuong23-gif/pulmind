import { useState } from "react";
import type { ChatMessage } from "../../types";
import { KGEvidenceDetails } from "./KGEvidenceDetails";
import { KGComparisonTable } from "./KGComparisonTable";
import "./kg-query.css";

const modes = { one_hop: "Quan hệ trực tiếp", multi_hop: "Chuỗi quan hệ", path: "Đường liên kết",
  compare: "So sánh", common: "Điểm chung", difference: "Điểm khác", inference: "Suy luận cấu trúc" };
const types: Record<string, string> = { Disease: "Bệnh", DiseaseSubtype: "Thể bệnh", Syndrome: "Hội chứng",
  Symptom: "Triệu chứng", ClinicalSign: "Dấu hiệu", Medication: "Thuốc", DrugClass: "Nhóm thuốc", ActiveIngredient: "Hoạt chất" };

export function KGQueryDetails({ message, busy, onConfirm, onSendQuestion }: {
  message: ChatMessage; busy: boolean; onConfirm?: (ids: string[]) => void;
  onSendQuestion?: (text: string) => void;
}) {
  const data = message.metadata;
  const clarification = data?.kg_clarification;
  const [choices, setChoices] = useState<Record<number, string>>({});
  const [typedNames, setTypedNames] = useState<Record<number, string>>({});
  const groups = clarification?.groups ?? [];
  const question = data?.resolved_question ?? "";
  const spans = groups.map(group => {
    const escaped = group.mention.trim().replace(/[.*+?$^{}()|[\]\\]/g, "\\$&");
    if (!escaped) return undefined;
    const matches = [...question.matchAll(new RegExp(
      `(?<![\\p{L}\\p{N}\\p{M}])${escaped}(?![\\p{L}\\p{N}\\p{M}])`, "giu",
    ))];
    return matches.length === 1 ? { start: matches[0].index!, length: matches[0][0].length } : undefined;
  });
  const orderedSpans = spans.filter(span => span !== undefined).sort((a, b) => a.start - b.start);
  const canType = Boolean(onSendQuestion && groups.length && spans.every(Boolean)
    && orderedSpans.every((span, i) => i === 0 || orderedSpans[i - 1].start + orderedSpans[i - 1].length <= span.start));
  const suggestions = clarification?.suggestions?.filter(s => s.trim()) ?? [];
  const canChoose = Boolean(clarification?.can_confirm && groups.length
    && groups.every(group => group.candidates.length));
  const showForm = canChoose || canType;
  const showClarificationDetails = Boolean(clarification && !showForm && groups.length);
  const showMode = Boolean(!clarification && (data?.kg_query?.mode || data?.kg_query?.preset_label));
  const showFallback = Boolean(!clarification && data?.retrieval_routing?.kg_evidence === "empty");
  const evidence = data?.kg_evidence;
  // KGEvidenceDetails renders content only for proofs, chains or paths.
  const showEvidence = Boolean(evidence && ((evidence.inferences?.length ?? 0)
    + (evidence.chains?.length ?? 0) + (evidence.paths?.length ?? 0) > 0));
  const showWarnings = Boolean(data?.kg_query?.warnings?.length);
  if (!showMode && !showFallback && !data?.kg_query?.truncated && !showEvidence
    && !data?.kg_comparison && !suggestions.length && !showForm
    && !showClarificationDetails && !showWarnings) return null;
  const manualOption = "__kg_manual_name__";
  const selection = groups.map((_, index) => choices[index] || "");
  const typing = selection.includes(manualOption);
  const names = selection.map((id, index) => id === manualOption ? typedNames[index]?.trim()
    : groups[index].candidates.find(candidate => candidate.id === id)?.name);
  const canSubmit = typing
    ? canType && names.every(Boolean)
    : canChoose && Boolean(onConfirm) && selection.every(Boolean) && new Set(selection).size === selection.length;

  function submit() {
    if (busy || !canSubmit) return;
    if (!typing) {
      onConfirm?.(selection);
      return;
    }
    let revised = question;
    const replacements = spans.map((span, index) => ({ ...span!, name: names[index]! }))
      .sort((a, b) => b.start - a.start);
    for (const { start, length, name } of replacements) {
      revised = revised.slice(0, start) + name + revised.slice(start + length);
    }
    onSendQuestion?.(revised);
  }
  return <section className="kg-query-details" aria-label="Thông tin truy xuất và bằng chứng">
    {data?.kg_query?.mode && !clarification && <p className="kg-query-mode">KG · {modes[data.kg_query.mode]}</p>}
    {!clarification && data?.kg_query?.concept_groups?.map(group =>
      <p key={group.members[0]?.id ?? group.name}>KG · {group.name} · truy vấn từ {group.members.length} nút ({group.members.map(member => types[member.type] ?? member.type).join(", ")})</p>)}
    {data?.kg_query?.preset_label && !clarification && <p>{data.kg_query.preset_label}</p>}
    {data?.retrieval_routing?.kg_evidence === "empty" && !clarification && <p>KG chưa đủ bằng chứng cho truy vấn này. Phần trả lời từ tài liệu bổ sung không phải kết luận đã được KG chứng minh.</p>}
    {data?.kg_query?.truncated && <p>Kết quả đã chạm giới hạn; các chuỗi hiển thị có thể chưa đầy đủ.</p>}
    {showEvidence && evidence && <KGEvidenceDetails evidence={evidence}/>}
    {!!suggestions.length && <div><p>Bạn có thể gửi lại một câu hỏi cụ thể, ví dụ:</p><ul>{suggestions.map((s,i)=><li key={i}>{s}</li>)}</ul></div>}
    {data?.kg_comparison && <KGComparisonTable comparison={data.kg_comparison} />}
    {showClarificationDetails && <div className="kg-clarification-summary">
      {groups.map((group, index) => {
        const unique = (group.candidate_count ?? group.candidates.length) === 1
          && group.candidates.length === 1 && group.candidates[0].matched_by !== "fuzzy";
        return <div key={index}>
          <p><strong>{unique ? "Đã nhận diện" : "Cần làm rõ"}:</strong> {group.mention}
            {unique && <> — {group.candidates[0].name} ({types[group.candidates[0].type] ?? group.candidates[0].type})</>}
          </p>
          {!unique && (group.candidates.length ? <>
            <p>Các tên có thể phù hợp; chưa chọn thực thể để truy vấn:</p>
            <ul>{group.candidates.map(candidate => <li key={candidate.id}>
              {candidate.name} ({types[candidate.type] ?? candidate.type})
            </li>)}</ul>
          </> : <p>Chưa tìm thấy tên này trong dữ liệu. Hãy dùng tên đầy đủ.</p>)}
        </div>;
      })}
      {data?.kg_query?.mode === "path" && groups.length < 2 &&
        <p>Chưa nhận diện đủ hai đầu mút. Hãy nêu tên đầy đủ của thực thể còn lại trong câu hỏi.</p>}
    </div>}
    {showForm && <fieldset disabled={busy || (!onConfirm && !onSendQuestion)}>
      <legend>Xác nhận tên cần tra cứu</legend>
      {groups.map((group, index) => <div key={index}><label>
        <span>{group.mention}</span>
        <select aria-label={`Thực thể ${index + 1}`} value={choices[index] || ""}
          onChange={event => setChoices(current => ({ ...current, [index]: event.target.value }))}>
          <option value="">Chọn tên phù hợp…</option>
          {group.candidates.map(candidate => <option key={candidate.id} value={candidate.id}>
            {candidate.name} ({types[candidate.type] ?? candidate.type})
          </option>)}
          {canType && <option value={manualOption}>Tự nhập tên thực thể</option>}
        </select>
      </label>
        {selection[index] === manualOption && <label>
          <span>Tên thay cho “{group.mention}”</span>
          <input type="text" value={typedNames[index] ?? ""}
            onChange={event => setTypedNames(current => ({ ...current, [index]: event.target.value }))} />
        </label>}
        {(group.candidate_count ?? 0) > group.candidates.length && <small>Danh sách được rút gọn. Bạn có thể viết lại câu hỏi với tên đầy đủ.</small>}
      </div>)}
      <button className="primary-button" type="button" disabled={busy || !canSubmit}
        onClick={submit}>Xác nhận và truy vấn</button>
      {!onConfirm && !onSendQuestion && <small>Lượt xác nhận này đã kết thúc. Hãy dùng lượt mới nhất hoặc gửi lại câu hỏi.</small>}
    </fieldset>}
    {!!data?.kg_query?.warnings?.length && <details>
      <summary>Giới hạn dữ liệu</summary>
      <ul>{data.kg_query.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
    </details>}

  </section>;
}
