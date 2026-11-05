import type { KGChatEvidence, KGChatFact } from "../../types";
import { SourceCitation } from "./EvidenceSources";
const labels:Record<string,string>={
 IS_A:"là một loại của",PART_OF:"là bộ phận của",HAS_SYMPTOM:"có triệu chứng",TREATS:"điều trị",TREATED_BY:"được điều trị bằng",INDICATED_FOR:"được chỉ định cho",
 HAS_REGIMEN:"có phác đồ",USES_MEDICATION:"sử dụng thuốc",HAS_TREATMENT_COMPONENT:"có thành phần điều trị",HAS_MEMBER:"có thành viên",BELONGS_TO_DRUG_CLASS:"thuộc nhóm thuốc",
 HAS_ADVERSE_EFFECT:"có tác dụng bất lợi",CONTRAINDICATED_IN:"chống chỉ định trong",HAS_CONTRAINDICATION:"có chống chỉ định",HAS_DOSE:"có liều",HAS_DOSAGE:"có liều dùng",
 HAS_ROUTE:"có đường dùng",HAS_FREQUENCY:"có tần suất",HAS_DURATION:"có thời gian",ABOUT_TOPIC:"đề cập chủ đề",COVERS_TOPIC:"bao quát chủ đề",HAS_RECOMMENDATION:"có khuyến cáo",
 RECOMMENDS:"khuyến cáo",RECOMMENDS_INTERVENTION:"khuyến cáo can thiệp",HAS_APPLICABILITY_CONDITION:"có điều kiện áp dụng",APPLIES_TO:"áp dụng cho",APPLIED_IN:"áp dụng tại",
 DIAGNOSED_BY:"được chẩn đoán bằng",DETECTS:"phát hiện",MEASURES:"đo lường",REQUIRES_SPECIMEN:"cần bệnh phẩm",HAS_CRITERION:"có tiêu chuẩn",HAS_THRESHOLD:"có ngưỡng",
 HAS_RESISTANCE_PROFILE:"có hồ sơ kháng",RESISTANT_TO:"kháng",CAUSED_BY:"do tác nhân",CAUSES:"gây",REQUIRES_MONITORING:"cần theo dõi",HAS_TREATMENT_STEP:"có bước điều trị",
 FOLLOWED_BY:"tiếp theo là",PREVENTS:"phòng ngừa",REDUCES_TRANSMISSION:"giảm lây truyền",HAS_TREATMENT_GOAL:"có mục tiêu điều trị",HAS_PROGNOSTIC_FACTOR:"có yếu tố tiên lượng",PREDICTS:"dự báo",
};
const relation=(name:string)=>labels[name]??name;
function Refs({refs}:{refs:number[]}){return <>{refs.map(n=><SourceCitation key={n} number={n}/>)}</>;}
function Fact({fact,refs}:{fact:KGChatFact;refs?:number[]}){return <div className="kg-proof-fact">
 <p><strong>{fact.subject.name}</strong> — <span title={fact.predicate}>{relation(fact.predicate)}</span> → <strong>{fact.object.name}</strong> <Refs refs={refs??fact.source_refs}/></p>
 {fact.assertions.map((assertion,index)=>{const properties=Object.entries(assertion.properties??{});if(!properties.length&&assertion.properties_valid!==false)return null;
 return <div key={index} className="kg-proof-conditions">{assertion.properties_valid===false&&<strong>Thuộc tính nguồn chưa hợp lệ.</strong>}
 {properties.length>0&&<p>Điều kiện/thuộc tính: {properties.map(([k,v])=>`${k}: ${typeof v==="object"?JSON.stringify(v):String(v)}`).join("; ")} <Refs refs={assertion.source_refs}/></p>}</div>;})}
 </div>;}
export function KGEvidenceDetails({evidence}:{evidence:KGChatEvidence}){
 const proofs=evidence.inferences??[],groups=[...(evidence.chains??[]),...(evidence.paths??[])];
 return <div className="kg-proof-panel">{proofs.length>0?<>
 <p>Kết luận dưới đây được suy ra theo quy tắc cấu trúc, chưa được ghi thành quan hệ mới trong CSDL.</p>
 {proofs.map((p,index)=><details className="kg-proof" key={index}>
 <summary>Kết luận suy ra {index+1}: {p.subject.name} — {relation(p.predicate)} → {p.object.name}</summary>
 <p>Quy tắc: {p.rule==="is_a_transitive"?"Phân loại bắc cầu":"Bộ phận bắc cầu"} · {p.hops} bước</p>
 <p>{p.evidence_scope==="cross_document"?"Phối hợp nhiều tài liệu; cần đối chiếu phạm vi nguồn.":"Các tiền đề có bằng chứng từ cùng tài liệu nguồn gốc."}</p>
 <ol aria-label="Các tiền đề suy luận">{p.premises.map((premise,i)=><li key={i}>{evidence.facts[premise.fact_index]?<Fact fact={evidence.facts[premise.fact_index]} refs={premise.source_refs}/>:"Thiếu tiền đề; không sử dụng kết luận này."}</li>)}</ol>
 </details>)}
 </>:groups.length>0?<details><summary>Chuỗi bằng chứng ({groups.length})</summary>
 <p>Mỗi bước là một quan hệ đã lưu, trình bày đúng chiều cạnh. Chuỗi liên kết không tự chứng minh quan hệ nhân quả giữa hai đầu.</p>
 {groups.map((group,index)=><div className="kg-proof" key={index}><strong>Chuỗi {index+1}</strong><ol>{group.fact_indices.map((position,i)=><li key={i}>{evidence.facts[position]?<Fact fact={evidence.facts[position]}/>:"Thiếu bước bằng chứng."}</li>)}</ol></div>)}
 </details>:null}</div>;
}
