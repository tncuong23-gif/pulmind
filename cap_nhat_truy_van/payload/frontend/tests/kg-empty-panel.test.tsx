import { expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { KGQueryDetails } from "../src/components/chat/KGQueryDetails";
import type { ChatMessage } from "../src/types";

function message(metadata: ChatMessage["metadata"]): ChatMessage {
  return { id: "kg-panel", role: "assistant", content: "Hãy làm rõ câu hỏi.", createdAt: "2026-11-05T00:00:00Z", metadata };
}

it("does not render a colored panel for clarification without any details", () => {
  const { container } = render(<KGQueryDetails busy={false} message={message({
    kg_query: { mode: "path" },
    kg_clarification: { message: "Hãy nêu hai tên.", can_confirm: false, groups: [], suggestions: [] },
  })} />);
  expect(container).toBeEmptyDOMElement();
});

it("does not render empty KG metadata or an evidence object with no proofs", () => {
  const { container } = render(<KGQueryDetails busy={false} message={message({
    kg_query: {}, kg_evidence: { facts: [], chains: [], paths: [], inferences: [] },
  })} />);
  expect(container).toBeEmptyDOMElement();
});

it("shows the recognized endpoint when the second one could not be identified", () => {
  render(<KGQueryDetails busy={false} message={message({ kg_query: { mode: "path" },
    kg_clarification: { message: "Hãy nêu hai tên.", can_confirm: false, groups: [
      { mention: "copd", candidates: [{ id: "COPD", name: "Bệnh phổi tắc nghẽn mạn tính", type: "Disease", matched_by: "alias" }] },
    ] },
  })} />);
  expect(screen.getByText("Đã nhận diện:")).toBeInTheDocument();
  expect(screen.getByText(/Bệnh phổi tắc nghẽn mạn tính/)).toBeInTheDocument();
  expect(screen.getByText(/Chưa nhận diện đủ hai đầu mút/)).toBeInTheDocument();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("shows ambiguous candidates as suggestions without silently selecting one", () => {
  render(<KGQueryDetails busy={false} message={message({ kg_query: { mode: "path" },
    kg_clarification: { message: "Làm rõ tên bệnh.", can_confirm: false, groups: [
      { mention: "lao", candidate_count: 2, candidates: [
        { id: "TB", name: "Bệnh lao", type: "Disease", matched_by: "fuzzy" },
        { id: "PTB", name: "Lao phổi", type: "Disease", matched_by: "fuzzy" },
      ] },
    ] },
  })} />);
  expect(screen.getByText("Cần làm rõ:")).toBeInTheDocument();
  expect(screen.getByText("Bệnh lao (Bệnh)")).toBeInTheDocument();
  expect(screen.getByText("Lao phổi (Bệnh)")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("keeps a useful suggestion even when there are no candidates", () => {
  render(<KGQueryDetails busy={false} message={message({
    kg_clarification: { message: "Cần tên đầy đủ.", can_confirm: false, groups: [],
      suggestions: ["Mối liên hệ giữa bệnh lao và COPD"] },
  })} />);
  expect(screen.getByText("Mối liên hệ giữa bệnh lao và COPD")).toBeInTheDocument();
});

it("does not show an empty confirmation form if the candidate list is empty", () => {
  const { container } = render(<KGQueryDetails busy={false} message={message({
    kg_clarification: { message: "Cần tên đầy đủ.", can_confirm: true, groups: [] },
  })} />);
  expect(container).toBeEmptyDOMElement();
});

it("offers manual entry after five candidates and replaces only the selected mention", () => {
  const sent: string[] = [];
  render(<KGQueryDetails busy={false} onSendQuestion={text => sent.push(text)} message={message({
    resolved_question: "Mối liên hệ giữa lao và COPD",
    kg_clarification: { message: "Chọn tên.", can_confirm: true, groups: [
      { mention: "lao", candidates: Array.from({ length: 5 }, (_, i) => ({
        id: "T" + i, name: "Bệnh " + i, type: "Disease", matched_by: "fuzzy",
      })) },
      { mention: "COPD", candidates: [{ id: "D", name: "COPD", type: "Disease", matched_by: "exact_name" }] },
    ] },
  })} />);
  const first = screen.getByRole<HTMLSelectElement>("combobox", { name: "Thực thể 1" });
  expect(Array.from(first.options).slice(1)).toHaveLength(6);
  expect(first.options[6].text).toBe("Tự nhập tên thực thể");
  fireEvent.change(first, { target: { value: first.options[6].value } });
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "lao phổi" } });
  fireEvent.change(screen.getByRole("combobox", { name: "Thực thể 2" }), { target: { value: "D" } });
  fireEvent.click(screen.getByRole("button", { name: "Xác nhận và truy vấn" }));
  expect(sent).toEqual(["Mối liên hệ giữa lao phổi và COPD"]);
});
