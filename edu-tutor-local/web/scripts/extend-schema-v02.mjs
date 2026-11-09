import { readFileSync, writeFileSync } from "node:fs";
const root = new URL("../../", import.meta.url);
const schema = JSON.parse(readFileSync(new URL("web/src/lesson_plan.schema.json", root), "utf8"));
const number = { type: "number", minimum: 0, maximum: 1 };
const id = { type: "string", minLength: 1, maxLength: 200 };
const object = (properties, required = Object.keys(properties)) => ({ type: "object", additionalProperties: false, properties, required });
const box = object({ x: number, y: number, width: { ...number, exclusiveMinimum: 0 }, height: { ...number, exclusiveMinimum: 0 } });
const timing = object({ start: number, end: number });
const actions = schema.properties.steps.items.properties.board_actions.items.oneOf;
for (const action of actions) {
  action.properties.timing = timing;
  if (["text", "table", "equation", "code"].includes(action.properties.type.const)) action.properties.layout = box;
}
const table = actions.find(action => action.properties.type.const === "table");
table.properties.table_name=id;
table.properties.row_ids = { type: "array", items: id, uniqueItems: true, maxItems: 200 };
table.properties.column_ids = { type: "array", items: id, uniqueItems: true, maxItems: 50 };
table.properties.cell_ids = { type: "array", items: { type: "array", items: id, uniqueItems: true, maxItems: 50 }, maxItems: 200 };
table.properties.rows.maxItems = 200;
table.properties.columns.maxItems = 50;
const highlight = actions.find(action=>action.properties.type.const === "highlight");
highlight.properties.cell_ids = {type:"array",items:id,uniqueItems:true,maxItems:500};
for (const type of ["line", "arrow", "rect", "ellipse", "circle", "brace"]) {
  const geometry = type === "line" || type === "arrow" ? object({ x1:number,y1:number,x2:number,y2:number }) : type === "circle" ? object({cx:number,cy:number,radius:{...number,exclusiveMinimum:0,maximum:.5}}) : box;
  const properties = {type:{const:type},element_id:id,slot:{enum:["main","left","right","bottom","overlay"]},geometry,stroke:{enum:["chalk","accent","warning"]},stroke_width:{type:"number",minimum:1,maximum:6},timing};
  if(type==="brace") properties.orientation={enum:["left","right","top","bottom"]};
  if(!actions.some(action=>action.properties.type.const===type && action.properties.geometry)) actions.push(object(properties,["type","element_id","geometry"]));
}
schema.properties.provenance.enum=Array.from(new Set([...schema.properties.provenance.enum,"tool_derived"]));
schema.properties.verification.properties.status.enum=Array.from(new Set([...schema.properties.verification.properties.status.enum,"execution_grounded","calculation_checked"]));
schema.properties.problem_revision={type:"integer",minimum:1};
schema.properties.source_message_id=id;
schema.properties.source_photo_id=id;
schema.properties.evidence_ref=object({message_id:id,problem_revision:{type:"integer",minimum:1},mode:{enum:["original","hypothesis","concept_example"]}});
const encoded=JSON.stringify(schema,null,2)+"\n";
for(const file of ["schemas/lesson_plan.schema.json","web/src/lesson_plan.schema.json","src/edu_tutor/lessons/assets/lesson_plan.schema.json"])writeFileSync(new URL(file,root),encoded);
