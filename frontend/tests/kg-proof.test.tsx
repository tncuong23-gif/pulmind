import {expect,it} from "vitest";
import {render,screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {KGQueryDetails} from "../src/components/chat/KGQueryDetails";
import {SourcesProvider} from "../src/components/chat/EvidenceSources";
import type {ChatMessage,KGChatEvidence} from "../src/types";
const evidence:KGChatEvidence={facts:[
 {subject:{name:"A",type:"Disease"},predicate:"IS_A",object:{name:"B",type:"Disease"},assertions:[],source_refs:[1]},
 {subject:{name:"B",type:"Disease"},predicate:"IS_A",object:{name:"C",type:"Disease"},assertions:[],source_refs:[2]}],
 chains:[{fact_indices:[0,1]}],inferences:[{kind:"inferred",rule:"is_a_transitive",subject:{name:"A",type:"Disease"},predicate:"IS_A",object:{name:"C",type:"Disease"},hops:2,evidence_scope:"same_document",fact_indices:[0,1],premises:[{fact_index:0,source_refs:[1]},{fact_index:1,source_refs:[2]}]}]};
function message():ChatMessage{return {id:"answer",role:"assistant",content:"Đáp án",createdAt:new Date().toISOString(),metadata:{kg_query:{mode:"inference"},kg_evidence:structuredClone(evidence),sources:[{number:1,title:"Nguồn A",text:"<img src=x onerror=alert(1)>"},{number:2,title:"Nguồn B",text:"Văn bản tiền đề thứ hai"}]}};}
it("shows inference premises with exact sources and escapes markup",async()=>{
 const u=userEvent.setup(),m=message();const {container}=render(<SourcesProvider sources={m.metadata?.sources}><KGQueryDetails message={m} busy={false}/></SourcesProvider>);
 expect(screen.getByText("KG · Suy luận cấu trúc")).toBeVisible();expect(screen.getByText(/chưa được ghi thành quan hệ mới/)).toBeVisible();
 await u.click(screen.getByText(/Kết luận suy ra 1/));expect(screen.getByRole("list",{name:"Các tiền đề suy luận"}).children.length).toBe(2);
 await u.click(screen.getByRole("button",{name:"Nguồn 2"}));expect(screen.getByText("Văn bản tiền đề thứ hai")).toBeVisible();
 await u.click(screen.getByRole("button",{name:"Đóng nguồn"}));await u.click(screen.getByRole("button",{name:"Nguồn 1"}));expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeVisible();expect(container.querySelector("img")).toBeNull();
});
it("shows stored chains and negation without inference label",async()=>{
 const u=userEvent.setup(),m=message();m.metadata!.kg_query={mode:"multi_hop",preset_label:"Chuỗi kiểm thử"};m.metadata!.kg_evidence!.inferences=[];
 m.metadata!.kg_evidence!.facts[0].assertions=[{properties:{negated:true,population:"Test group"},properties_valid:true,source_refs:[1]}];
 render(<SourcesProvider sources={m.metadata?.sources}><KGQueryDetails message={m} busy={false}/></SourcesProvider>);
 await u.click(screen.getByText("Chuỗi bằng chứng (1)"));expect(screen.getByText(/không tự chứng minh quan hệ nhân quả/)).toBeVisible();expect(screen.getByText(/negated: true/)).toBeVisible();expect(screen.queryByText(/Kết luận suy ra/)).not.toBeInTheDocument();
});
it("suggests rephrasing without entity confirm",()=>{
 const m=message();m.metadata={kg_query:{mode:"one_hop"},kg_clarification:{message:"Chọn nội dung",can_confirm:false,groups:[],suggestions:["Phác đồ của A có liều dùng nào?","Phác đồ của A có tác dụng phụ nào?"]}};
 render(<KGQueryDetails message={m} busy={false}/>);expect(screen.getByText("Phác đồ của A có liều dùng nào?")).toBeVisible();expect(screen.queryByRole("button",{name:"Xác nhận và truy vấn"})).not.toBeInTheDocument();
});
it("does not show filtered proof when RAG supplies answer",()=>{
 const m=message();m.metadata!.kg_evidence=null;m.metadata!.retrieval_routing={kg_evidence:"empty",effective_route:"GENERAL_MEDICAL_QUERY"};render(<KGQueryDetails message={m} busy={false}/>);
 expect(screen.getByText(/không phải kết luận đã được KG chứng minh/)).toBeVisible();expect(screen.queryByText(/Kết luận suy ra/)).not.toBeInTheDocument();
});
