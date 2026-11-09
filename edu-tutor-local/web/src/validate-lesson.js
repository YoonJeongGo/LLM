// Generated from lesson_plan.schema.json. Do not edit by hand.
"use strict";
export const validate = validate20;
export default validate20;
const schema31 = {"type":"object","additionalProperties":false,"properties":{"schema_version":{"const":"1.0"},"lesson_id":{"type":"string","minLength":1},"title":{"type":"string","minLength":1},"goal":{"type":"string","minLength":1},"question_text":{"type":"string","minLength":1},"problem_source":{"enum":["typed_user_input","confirmed_image","self_authored_example"]},"provenance":{"enum":["demo_fixture","model_generated","human_authored","tool_derived"]},"source_refs":{"type":"array","items":{"type":"object","additionalProperties":false,"properties":{"document_id":{"type":"string","minLength":1},"chunk_id":{"type":"string","minLength":1},"label":{"type":"string","minLength":1}},"required":["document_id","chunk_id","label"]}},"verification":{"type":"object","additionalProperties":false,"properties":{"status":{"enum":["unverified","fixture_sql_checked","sql_executed","human_reviewed","execution_grounded","calculation_checked"]},"scope":{"type":"string","minLength":1},"limitations":{"type":"array","items":{"type":"string","minLength":1}}},"required":["status","scope","limitations"]},"steps":{"type":"array","items":{"type":"object","additionalProperties":false,"properties":{"id":{"type":"string","minLength":1},"title":{"type":"string","minLength":1},"speech":{"type":"string","minLength":1},"board_actions":{"type":"array","items":{"oneOf":[{"type":"object","properties":{"type":{"const":"text"},"element_id":{"type":"string","minLength":1},"slot":{"enum":["main","left","right","bottom","overlay"]},"text":{"type":"string","minLength":1},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]},"layout":{"type":"object","additionalProperties":false,"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"width":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0},"height":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0}},"required":["x","y","width","height"]}},"required":["type","element_id","slot","text"],"additionalProperties":false},{"type":"object","properties":{"type":{"const":"equation"},"element_id":{"type":"string","minLength":1},"slot":{"enum":["main","left","right","bottom","overlay"]},"latex":{"type":"string","minLength":1},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]},"layout":{"type":"object","additionalProperties":false,"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"width":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0},"height":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0}},"required":["x","y","width","height"]}},"required":["type","element_id","slot","latex"],"additionalProperties":false},{"type":"object","properties":{"type":{"const":"table"},"element_id":{"type":"string","minLength":1},"slot":{"enum":["main","left","right","bottom","overlay"]},"columns":{"type":"array","minItems":1,"items":{"type":"string"},"maxItems":50},"rows":{"type":"array","items":{"type":"array","items":{"type":["string","number","boolean","null"]}},"maxItems":200},"caption":{"type":"string"},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]},"layout":{"type":"object","additionalProperties":false,"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"width":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0},"height":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0}},"required":["x","y","width","height"]},"row_ids":{"type":"array","items":{"type":"string","minLength":1,"maxLength":200},"uniqueItems":true,"maxItems":200},"column_ids":{"type":"array","items":{"type":"string","minLength":1,"maxLength":200},"uniqueItems":true,"maxItems":50},"cell_ids":{"type":"array","items":{"type":"array","items":{"type":"string","minLength":1,"maxLength":200},"uniqueItems":true,"maxItems":50},"maxItems":200},"table_name":{"type":"string","minLength":1,"maxLength":200}},"required":["type","element_id","slot","columns","rows"],"additionalProperties":false},{"type":"object","properties":{"type":{"const":"code"},"element_id":{"type":"string","minLength":1},"slot":{"enum":["main","left","right","bottom","overlay"]},"language":{"enum":["sql","python","java","c","text"]},"code":{"type":"string","minLength":1},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]},"layout":{"type":"object","additionalProperties":false,"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"width":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0},"height":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0}},"required":["x","y","width","height"]}},"required":["type","element_id","slot","language","code"],"additionalProperties":false},{"type":"object","properties":{"type":{"const":"highlight"},"element_id":{"type":"string","minLength":1},"slot":{"enum":["main","left","right","bottom","overlay"]},"target_element_id":{"type":"string","minLength":1},"row_indices":{"type":"array","items":{"type":"integer","minimum":0}},"column_indices":{"type":"array","items":{"type":"integer","minimum":0}},"style":{"enum":["outline","underline","background"]},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]},"cell_ids":{"type":"array","items":{"type":"string","minLength":1,"maxLength":200},"uniqueItems":true,"maxItems":500}},"required":["type","target_element_id","style"],"additionalProperties":false},{"type":"object","properties":{"type":{"const":"arrow"},"element_id":{"type":"string","minLength":1},"slot":{"enum":["main","left","right","bottom","overlay"]},"from_element_id":{"type":"string"},"to_element_id":{"type":"string"},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]}},"required":["type","element_id","from_element_id","to_element_id"],"additionalProperties":false},{"type":"object","properties":{"type":{"const":"clear"},"element_id":{"type":"string","minLength":1},"slot":{"enum":["main","left","right","bottom","overlay"]},"target":{"type":"string","minLength":1},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]}},"required":["type","target"],"additionalProperties":false},{"type":"object","additionalProperties":false,"properties":{"type":{"const":"line"},"element_id":{"type":"string","minLength":1,"maxLength":200},"slot":{"enum":["main","left","right","bottom","overlay"]},"geometry":{"type":"object","additionalProperties":false,"properties":{"x1":{"type":"number","minimum":0,"maximum":1},"y1":{"type":"number","minimum":0,"maximum":1},"x2":{"type":"number","minimum":0,"maximum":1},"y2":{"type":"number","minimum":0,"maximum":1}},"required":["x1","y1","x2","y2"]},"stroke":{"enum":["chalk","accent","warning"]},"stroke_width":{"type":"number","minimum":1,"maximum":6},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]}},"required":["type","element_id","geometry"]},{"type":"object","additionalProperties":false,"properties":{"type":{"const":"arrow"},"element_id":{"type":"string","minLength":1,"maxLength":200},"slot":{"enum":["main","left","right","bottom","overlay"]},"geometry":{"type":"object","additionalProperties":false,"properties":{"x1":{"type":"number","minimum":0,"maximum":1},"y1":{"type":"number","minimum":0,"maximum":1},"x2":{"type":"number","minimum":0,"maximum":1},"y2":{"type":"number","minimum":0,"maximum":1}},"required":["x1","y1","x2","y2"]},"stroke":{"enum":["chalk","accent","warning"]},"stroke_width":{"type":"number","minimum":1,"maximum":6},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]}},"required":["type","element_id","geometry"]},{"type":"object","additionalProperties":false,"properties":{"type":{"const":"rect"},"element_id":{"type":"string","minLength":1,"maxLength":200},"slot":{"enum":["main","left","right","bottom","overlay"]},"geometry":{"type":"object","additionalProperties":false,"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"width":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0},"height":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0}},"required":["x","y","width","height"]},"stroke":{"enum":["chalk","accent","warning"]},"stroke_width":{"type":"number","minimum":1,"maximum":6},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]}},"required":["type","element_id","geometry"]},{"type":"object","additionalProperties":false,"properties":{"type":{"const":"ellipse"},"element_id":{"type":"string","minLength":1,"maxLength":200},"slot":{"enum":["main","left","right","bottom","overlay"]},"geometry":{"type":"object","additionalProperties":false,"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"width":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0},"height":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0}},"required":["x","y","width","height"]},"stroke":{"enum":["chalk","accent","warning"]},"stroke_width":{"type":"number","minimum":1,"maximum":6},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]}},"required":["type","element_id","geometry"]},{"type":"object","additionalProperties":false,"properties":{"type":{"const":"circle"},"element_id":{"type":"string","minLength":1,"maxLength":200},"slot":{"enum":["main","left","right","bottom","overlay"]},"geometry":{"type":"object","additionalProperties":false,"properties":{"cx":{"type":"number","minimum":0,"maximum":1},"cy":{"type":"number","minimum":0,"maximum":1},"radius":{"type":"number","minimum":0,"maximum":0.5,"exclusiveMinimum":0}},"required":["cx","cy","radius"]},"stroke":{"enum":["chalk","accent","warning"]},"stroke_width":{"type":"number","minimum":1,"maximum":6},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]}},"required":["type","element_id","geometry"]},{"type":"object","additionalProperties":false,"properties":{"type":{"const":"brace"},"element_id":{"type":"string","minLength":1,"maxLength":200},"slot":{"enum":["main","left","right","bottom","overlay"]},"geometry":{"type":"object","additionalProperties":false,"properties":{"x":{"type":"number","minimum":0,"maximum":1},"y":{"type":"number","minimum":0,"maximum":1},"width":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0},"height":{"type":"number","minimum":0,"maximum":1,"exclusiveMinimum":0}},"required":["x","y","width","height"]},"stroke":{"enum":["chalk","accent","warning"]},"stroke_width":{"type":"number","minimum":1,"maximum":6},"timing":{"type":"object","additionalProperties":false,"properties":{"start":{"type":"number","minimum":0,"maximum":1},"end":{"type":"number","minimum":0,"maximum":1}},"required":["start","end"]},"orientation":{"enum":["left","right","top","bottom"]}},"required":["type","element_id","geometry"]}]}},"gesture":{"type":"object","additionalProperties":false,"properties":{"kind":{"enum":["idle","look_board","point","write","explain"]},"target_element_id":{"type":["string","null"]}},"required":["kind","target_element_id"]}},"required":["id","title","speech","board_actions","gesture"]},"minItems":1,"maxItems":12},"final_summary":{"type":"string","minLength":1},"problem_revision":{"type":"integer","minimum":1},"source_message_id":{"type":"string","minLength":1,"maxLength":200},"source_photo_id":{"type":"string","minLength":1,"maxLength":200},"evidence_ref":{"type":"object","additionalProperties":false,"properties":{"message_id":{"type":"string","minLength":1,"maxLength":200},"problem_revision":{"type":"integer","minimum":1},"mode":{"enum":["original","hypothesis","concept_example"]}},"required":["message_id","problem_revision","mode"]}},"required":["schema_version","lesson_id","title","goal","question_text","problem_source","provenance","source_refs","verification","steps","final_summary"],"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"urn:edu-tutor:lesson-plan:1","title":"AI 강의실 강의 계획 v1"};
const func1 = Object.prototype.hasOwnProperty;
import func2 from "ajv/dist/runtime/ucs2length.js";

function validate20(data, {instancePath="", parentData, parentDataProperty, rootData=data, dynamicAnchors={}}={}){
/*# sourceURL="urn:edu-tutor:lesson-plan:1" */;
let vErrors = null;
let errors = 0;
const evaluated0 = validate20.evaluated;
if(evaluated0.dynamicProps){
evaluated0.props = undefined;
}
if(evaluated0.dynamicItems){
evaluated0.items = undefined;
}
if(data && typeof data == "object" && !Array.isArray(data)){
if(data.schema_version === undefined){
const err0 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "schema_version"},message:"must have required property '"+"schema_version"+"'"};
if(vErrors === null){
vErrors = [err0];
}
else {
vErrors.push(err0);
}
errors++;
}
if(data.lesson_id === undefined){
const err1 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "lesson_id"},message:"must have required property '"+"lesson_id"+"'"};
if(vErrors === null){
vErrors = [err1];
}
else {
vErrors.push(err1);
}
errors++;
}
if(data.title === undefined){
const err2 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "title"},message:"must have required property '"+"title"+"'"};
if(vErrors === null){
vErrors = [err2];
}
else {
vErrors.push(err2);
}
errors++;
}
if(data.goal === undefined){
const err3 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "goal"},message:"must have required property '"+"goal"+"'"};
if(vErrors === null){
vErrors = [err3];
}
else {
vErrors.push(err3);
}
errors++;
}
if(data.question_text === undefined){
const err4 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "question_text"},message:"must have required property '"+"question_text"+"'"};
if(vErrors === null){
vErrors = [err4];
}
else {
vErrors.push(err4);
}
errors++;
}
if(data.problem_source === undefined){
const err5 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "problem_source"},message:"must have required property '"+"problem_source"+"'"};
if(vErrors === null){
vErrors = [err5];
}
else {
vErrors.push(err5);
}
errors++;
}
if(data.provenance === undefined){
const err6 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "provenance"},message:"must have required property '"+"provenance"+"'"};
if(vErrors === null){
vErrors = [err6];
}
else {
vErrors.push(err6);
}
errors++;
}
if(data.source_refs === undefined){
const err7 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "source_refs"},message:"must have required property '"+"source_refs"+"'"};
if(vErrors === null){
vErrors = [err7];
}
else {
vErrors.push(err7);
}
errors++;
}
if(data.verification === undefined){
const err8 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "verification"},message:"must have required property '"+"verification"+"'"};
if(vErrors === null){
vErrors = [err8];
}
else {
vErrors.push(err8);
}
errors++;
}
if(data.steps === undefined){
const err9 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "steps"},message:"must have required property '"+"steps"+"'"};
if(vErrors === null){
vErrors = [err9];
}
else {
vErrors.push(err9);
}
errors++;
}
if(data.final_summary === undefined){
const err10 = {instancePath,schemaPath:"#/required",keyword:"required",params:{missingProperty: "final_summary"},message:"must have required property '"+"final_summary"+"'"};
if(vErrors === null){
vErrors = [err10];
}
else {
vErrors.push(err10);
}
errors++;
}
for(const key0 in data){
if(!(func1.call(schema31.properties, key0))){
const err11 = {instancePath,schemaPath:"#/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key0},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err11];
}
else {
vErrors.push(err11);
}
errors++;
}
}
if(data.schema_version !== undefined){
if("1.0" !== data.schema_version){
const err12 = {instancePath:instancePath+"/schema_version",schemaPath:"#/properties/schema_version/const",keyword:"const",params:{allowedValue: "1.0"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err12];
}
else {
vErrors.push(err12);
}
errors++;
}
}
if(data.lesson_id !== undefined){
let data1 = data.lesson_id;
if(typeof data1 === "string"){
if(func2(data1) < 1){
const err13 = {instancePath:instancePath+"/lesson_id",schemaPath:"#/properties/lesson_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err13];
}
else {
vErrors.push(err13);
}
errors++;
}
}
else {
const err14 = {instancePath:instancePath+"/lesson_id",schemaPath:"#/properties/lesson_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err14];
}
else {
vErrors.push(err14);
}
errors++;
}
}
if(data.title !== undefined){
let data2 = data.title;
if(typeof data2 === "string"){
if(func2(data2) < 1){
const err15 = {instancePath:instancePath+"/title",schemaPath:"#/properties/title/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err15];
}
else {
vErrors.push(err15);
}
errors++;
}
}
else {
const err16 = {instancePath:instancePath+"/title",schemaPath:"#/properties/title/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err16];
}
else {
vErrors.push(err16);
}
errors++;
}
}
if(data.goal !== undefined){
let data3 = data.goal;
if(typeof data3 === "string"){
if(func2(data3) < 1){
const err17 = {instancePath:instancePath+"/goal",schemaPath:"#/properties/goal/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err17];
}
else {
vErrors.push(err17);
}
errors++;
}
}
else {
const err18 = {instancePath:instancePath+"/goal",schemaPath:"#/properties/goal/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err18];
}
else {
vErrors.push(err18);
}
errors++;
}
}
if(data.question_text !== undefined){
let data4 = data.question_text;
if(typeof data4 === "string"){
if(func2(data4) < 1){
const err19 = {instancePath:instancePath+"/question_text",schemaPath:"#/properties/question_text/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err19];
}
else {
vErrors.push(err19);
}
errors++;
}
}
else {
const err20 = {instancePath:instancePath+"/question_text",schemaPath:"#/properties/question_text/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err20];
}
else {
vErrors.push(err20);
}
errors++;
}
}
if(data.problem_source !== undefined){
let data5 = data.problem_source;
if(!(((data5 === "typed_user_input") || (data5 === "confirmed_image")) || (data5 === "self_authored_example"))){
const err21 = {instancePath:instancePath+"/problem_source",schemaPath:"#/properties/problem_source/enum",keyword:"enum",params:{allowedValues: schema31.properties.problem_source.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err21];
}
else {
vErrors.push(err21);
}
errors++;
}
}
if(data.provenance !== undefined){
let data6 = data.provenance;
if(!((((data6 === "demo_fixture") || (data6 === "model_generated")) || (data6 === "human_authored")) || (data6 === "tool_derived"))){
const err22 = {instancePath:instancePath+"/provenance",schemaPath:"#/properties/provenance/enum",keyword:"enum",params:{allowedValues: schema31.properties.provenance.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err22];
}
else {
vErrors.push(err22);
}
errors++;
}
}
if(data.source_refs !== undefined){
let data7 = data.source_refs;
if(Array.isArray(data7)){
const len0 = data7.length;
for(let i0=0; i0<len0; i0++){
let data8 = data7[i0];
if(data8 && typeof data8 == "object" && !Array.isArray(data8)){
if(data8.document_id === undefined){
const err23 = {instancePath:instancePath+"/source_refs/" + i0,schemaPath:"#/properties/source_refs/items/required",keyword:"required",params:{missingProperty: "document_id"},message:"must have required property '"+"document_id"+"'"};
if(vErrors === null){
vErrors = [err23];
}
else {
vErrors.push(err23);
}
errors++;
}
if(data8.chunk_id === undefined){
const err24 = {instancePath:instancePath+"/source_refs/" + i0,schemaPath:"#/properties/source_refs/items/required",keyword:"required",params:{missingProperty: "chunk_id"},message:"must have required property '"+"chunk_id"+"'"};
if(vErrors === null){
vErrors = [err24];
}
else {
vErrors.push(err24);
}
errors++;
}
if(data8.label === undefined){
const err25 = {instancePath:instancePath+"/source_refs/" + i0,schemaPath:"#/properties/source_refs/items/required",keyword:"required",params:{missingProperty: "label"},message:"must have required property '"+"label"+"'"};
if(vErrors === null){
vErrors = [err25];
}
else {
vErrors.push(err25);
}
errors++;
}
for(const key1 in data8){
if(!(((key1 === "document_id") || (key1 === "chunk_id")) || (key1 === "label"))){
const err26 = {instancePath:instancePath+"/source_refs/" + i0,schemaPath:"#/properties/source_refs/items/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key1},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err26];
}
else {
vErrors.push(err26);
}
errors++;
}
}
if(data8.document_id !== undefined){
let data9 = data8.document_id;
if(typeof data9 === "string"){
if(func2(data9) < 1){
const err27 = {instancePath:instancePath+"/source_refs/" + i0+"/document_id",schemaPath:"#/properties/source_refs/items/properties/document_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err27];
}
else {
vErrors.push(err27);
}
errors++;
}
}
else {
const err28 = {instancePath:instancePath+"/source_refs/" + i0+"/document_id",schemaPath:"#/properties/source_refs/items/properties/document_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err28];
}
else {
vErrors.push(err28);
}
errors++;
}
}
if(data8.chunk_id !== undefined){
let data10 = data8.chunk_id;
if(typeof data10 === "string"){
if(func2(data10) < 1){
const err29 = {instancePath:instancePath+"/source_refs/" + i0+"/chunk_id",schemaPath:"#/properties/source_refs/items/properties/chunk_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err29];
}
else {
vErrors.push(err29);
}
errors++;
}
}
else {
const err30 = {instancePath:instancePath+"/source_refs/" + i0+"/chunk_id",schemaPath:"#/properties/source_refs/items/properties/chunk_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err30];
}
else {
vErrors.push(err30);
}
errors++;
}
}
if(data8.label !== undefined){
let data11 = data8.label;
if(typeof data11 === "string"){
if(func2(data11) < 1){
const err31 = {instancePath:instancePath+"/source_refs/" + i0+"/label",schemaPath:"#/properties/source_refs/items/properties/label/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err31];
}
else {
vErrors.push(err31);
}
errors++;
}
}
else {
const err32 = {instancePath:instancePath+"/source_refs/" + i0+"/label",schemaPath:"#/properties/source_refs/items/properties/label/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err32];
}
else {
vErrors.push(err32);
}
errors++;
}
}
}
else {
const err33 = {instancePath:instancePath+"/source_refs/" + i0,schemaPath:"#/properties/source_refs/items/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err33];
}
else {
vErrors.push(err33);
}
errors++;
}
}
}
else {
const err34 = {instancePath:instancePath+"/source_refs",schemaPath:"#/properties/source_refs/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err34];
}
else {
vErrors.push(err34);
}
errors++;
}
}
if(data.verification !== undefined){
let data12 = data.verification;
if(data12 && typeof data12 == "object" && !Array.isArray(data12)){
if(data12.status === undefined){
const err35 = {instancePath:instancePath+"/verification",schemaPath:"#/properties/verification/required",keyword:"required",params:{missingProperty: "status"},message:"must have required property '"+"status"+"'"};
if(vErrors === null){
vErrors = [err35];
}
else {
vErrors.push(err35);
}
errors++;
}
if(data12.scope === undefined){
const err36 = {instancePath:instancePath+"/verification",schemaPath:"#/properties/verification/required",keyword:"required",params:{missingProperty: "scope"},message:"must have required property '"+"scope"+"'"};
if(vErrors === null){
vErrors = [err36];
}
else {
vErrors.push(err36);
}
errors++;
}
if(data12.limitations === undefined){
const err37 = {instancePath:instancePath+"/verification",schemaPath:"#/properties/verification/required",keyword:"required",params:{missingProperty: "limitations"},message:"must have required property '"+"limitations"+"'"};
if(vErrors === null){
vErrors = [err37];
}
else {
vErrors.push(err37);
}
errors++;
}
for(const key2 in data12){
if(!(((key2 === "status") || (key2 === "scope")) || (key2 === "limitations"))){
const err38 = {instancePath:instancePath+"/verification",schemaPath:"#/properties/verification/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key2},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err38];
}
else {
vErrors.push(err38);
}
errors++;
}
}
if(data12.status !== undefined){
let data13 = data12.status;
if(!((((((data13 === "unverified") || (data13 === "fixture_sql_checked")) || (data13 === "sql_executed")) || (data13 === "human_reviewed")) || (data13 === "execution_grounded")) || (data13 === "calculation_checked"))){
const err39 = {instancePath:instancePath+"/verification/status",schemaPath:"#/properties/verification/properties/status/enum",keyword:"enum",params:{allowedValues: schema31.properties.verification.properties.status.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err39];
}
else {
vErrors.push(err39);
}
errors++;
}
}
if(data12.scope !== undefined){
let data14 = data12.scope;
if(typeof data14 === "string"){
if(func2(data14) < 1){
const err40 = {instancePath:instancePath+"/verification/scope",schemaPath:"#/properties/verification/properties/scope/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err40];
}
else {
vErrors.push(err40);
}
errors++;
}
}
else {
const err41 = {instancePath:instancePath+"/verification/scope",schemaPath:"#/properties/verification/properties/scope/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err41];
}
else {
vErrors.push(err41);
}
errors++;
}
}
if(data12.limitations !== undefined){
let data15 = data12.limitations;
if(Array.isArray(data15)){
const len1 = data15.length;
for(let i1=0; i1<len1; i1++){
let data16 = data15[i1];
if(typeof data16 === "string"){
if(func2(data16) < 1){
const err42 = {instancePath:instancePath+"/verification/limitations/" + i1,schemaPath:"#/properties/verification/properties/limitations/items/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err42];
}
else {
vErrors.push(err42);
}
errors++;
}
}
else {
const err43 = {instancePath:instancePath+"/verification/limitations/" + i1,schemaPath:"#/properties/verification/properties/limitations/items/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err43];
}
else {
vErrors.push(err43);
}
errors++;
}
}
}
else {
const err44 = {instancePath:instancePath+"/verification/limitations",schemaPath:"#/properties/verification/properties/limitations/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err44];
}
else {
vErrors.push(err44);
}
errors++;
}
}
}
else {
const err45 = {instancePath:instancePath+"/verification",schemaPath:"#/properties/verification/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err45];
}
else {
vErrors.push(err45);
}
errors++;
}
}
if(data.steps !== undefined){
let data17 = data.steps;
if(Array.isArray(data17)){
if(data17.length > 12){
const err46 = {instancePath:instancePath+"/steps",schemaPath:"#/properties/steps/maxItems",keyword:"maxItems",params:{limit: 12},message:"must NOT have more than 12 items"};
if(vErrors === null){
vErrors = [err46];
}
else {
vErrors.push(err46);
}
errors++;
}
if(data17.length < 1){
const err47 = {instancePath:instancePath+"/steps",schemaPath:"#/properties/steps/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err47];
}
else {
vErrors.push(err47);
}
errors++;
}
const len2 = data17.length;
for(let i2=0; i2<len2; i2++){
let data18 = data17[i2];
if(data18 && typeof data18 == "object" && !Array.isArray(data18)){
if(data18.id === undefined){
const err48 = {instancePath:instancePath+"/steps/" + i2,schemaPath:"#/properties/steps/items/required",keyword:"required",params:{missingProperty: "id"},message:"must have required property '"+"id"+"'"};
if(vErrors === null){
vErrors = [err48];
}
else {
vErrors.push(err48);
}
errors++;
}
if(data18.title === undefined){
const err49 = {instancePath:instancePath+"/steps/" + i2,schemaPath:"#/properties/steps/items/required",keyword:"required",params:{missingProperty: "title"},message:"must have required property '"+"title"+"'"};
if(vErrors === null){
vErrors = [err49];
}
else {
vErrors.push(err49);
}
errors++;
}
if(data18.speech === undefined){
const err50 = {instancePath:instancePath+"/steps/" + i2,schemaPath:"#/properties/steps/items/required",keyword:"required",params:{missingProperty: "speech"},message:"must have required property '"+"speech"+"'"};
if(vErrors === null){
vErrors = [err50];
}
else {
vErrors.push(err50);
}
errors++;
}
if(data18.board_actions === undefined){
const err51 = {instancePath:instancePath+"/steps/" + i2,schemaPath:"#/properties/steps/items/required",keyword:"required",params:{missingProperty: "board_actions"},message:"must have required property '"+"board_actions"+"'"};
if(vErrors === null){
vErrors = [err51];
}
else {
vErrors.push(err51);
}
errors++;
}
if(data18.gesture === undefined){
const err52 = {instancePath:instancePath+"/steps/" + i2,schemaPath:"#/properties/steps/items/required",keyword:"required",params:{missingProperty: "gesture"},message:"must have required property '"+"gesture"+"'"};
if(vErrors === null){
vErrors = [err52];
}
else {
vErrors.push(err52);
}
errors++;
}
for(const key3 in data18){
if(!(((((key3 === "id") || (key3 === "title")) || (key3 === "speech")) || (key3 === "board_actions")) || (key3 === "gesture"))){
const err53 = {instancePath:instancePath+"/steps/" + i2,schemaPath:"#/properties/steps/items/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key3},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err53];
}
else {
vErrors.push(err53);
}
errors++;
}
}
if(data18.id !== undefined){
let data19 = data18.id;
if(typeof data19 === "string"){
if(func2(data19) < 1){
const err54 = {instancePath:instancePath+"/steps/" + i2+"/id",schemaPath:"#/properties/steps/items/properties/id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err54];
}
else {
vErrors.push(err54);
}
errors++;
}
}
else {
const err55 = {instancePath:instancePath+"/steps/" + i2+"/id",schemaPath:"#/properties/steps/items/properties/id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err55];
}
else {
vErrors.push(err55);
}
errors++;
}
}
if(data18.title !== undefined){
let data20 = data18.title;
if(typeof data20 === "string"){
if(func2(data20) < 1){
const err56 = {instancePath:instancePath+"/steps/" + i2+"/title",schemaPath:"#/properties/steps/items/properties/title/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err56];
}
else {
vErrors.push(err56);
}
errors++;
}
}
else {
const err57 = {instancePath:instancePath+"/steps/" + i2+"/title",schemaPath:"#/properties/steps/items/properties/title/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err57];
}
else {
vErrors.push(err57);
}
errors++;
}
}
if(data18.speech !== undefined){
let data21 = data18.speech;
if(typeof data21 === "string"){
if(func2(data21) < 1){
const err58 = {instancePath:instancePath+"/steps/" + i2+"/speech",schemaPath:"#/properties/steps/items/properties/speech/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err58];
}
else {
vErrors.push(err58);
}
errors++;
}
}
else {
const err59 = {instancePath:instancePath+"/steps/" + i2+"/speech",schemaPath:"#/properties/steps/items/properties/speech/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err59];
}
else {
vErrors.push(err59);
}
errors++;
}
}
if(data18.board_actions !== undefined){
let data22 = data18.board_actions;
if(Array.isArray(data22)){
const len3 = data22.length;
for(let i3=0; i3<len3; i3++){
let data23 = data22[i3];
const _errs48 = errors;
let valid12 = false;
let passing0 = null;
const _errs49 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err60 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err60];
}
else {
vErrors.push(err60);
}
errors++;
}
if(data23.element_id === undefined){
const err61 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err61];
}
else {
vErrors.push(err61);
}
errors++;
}
if(data23.slot === undefined){
const err62 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/required",keyword:"required",params:{missingProperty: "slot"},message:"must have required property '"+"slot"+"'"};
if(vErrors === null){
vErrors = [err62];
}
else {
vErrors.push(err62);
}
errors++;
}
if(data23.text === undefined){
const err63 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/required",keyword:"required",params:{missingProperty: "text"},message:"must have required property '"+"text"+"'"};
if(vErrors === null){
vErrors = [err63];
}
else {
vErrors.push(err63);
}
errors++;
}
for(const key4 in data23){
if(!((((((key4 === "type") || (key4 === "element_id")) || (key4 === "slot")) || (key4 === "text")) || (key4 === "timing")) || (key4 === "layout"))){
const err64 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key4},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err64];
}
else {
vErrors.push(err64);
}
errors++;
}
}
if(data23.type !== undefined){
if("text" !== data23.type){
const err65 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/type/const",keyword:"const",params:{allowedValue: "text"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err65];
}
else {
vErrors.push(err65);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data25 = data23.element_id;
if(typeof data25 === "string"){
if(func2(data25) < 1){
const err66 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err66];
}
else {
vErrors.push(err66);
}
errors++;
}
}
else {
const err67 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err67];
}
else {
vErrors.push(err67);
}
errors++;
}
}
if(data23.slot !== undefined){
let data26 = data23.slot;
if(!(((((data26 === "main") || (data26 === "left")) || (data26 === "right")) || (data26 === "bottom")) || (data26 === "overlay"))){
const err68 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[0].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err68];
}
else {
vErrors.push(err68);
}
errors++;
}
}
if(data23.text !== undefined){
let data27 = data23.text;
if(typeof data27 === "string"){
if(func2(data27) < 1){
const err69 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/text",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/text/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err69];
}
else {
vErrors.push(err69);
}
errors++;
}
}
else {
const err70 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/text",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/text/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err70];
}
else {
vErrors.push(err70);
}
errors++;
}
}
if(data23.timing !== undefined){
let data28 = data23.timing;
if(data28 && typeof data28 == "object" && !Array.isArray(data28)){
if(data28.start === undefined){
const err71 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err71];
}
else {
vErrors.push(err71);
}
errors++;
}
if(data28.end === undefined){
const err72 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err72];
}
else {
vErrors.push(err72);
}
errors++;
}
for(const key5 in data28){
if(!((key5 === "start") || (key5 === "end"))){
const err73 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key5},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err73];
}
else {
vErrors.push(err73);
}
errors++;
}
}
if(data28.start !== undefined){
let data29 = data28.start;
if(typeof data29 == "number"){
if(data29 > 1 || isNaN(data29)){
const err74 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err74];
}
else {
vErrors.push(err74);
}
errors++;
}
if(data29 < 0 || isNaN(data29)){
const err75 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err75];
}
else {
vErrors.push(err75);
}
errors++;
}
}
else {
const err76 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err76];
}
else {
vErrors.push(err76);
}
errors++;
}
}
if(data28.end !== undefined){
let data30 = data28.end;
if(typeof data30 == "number"){
if(data30 > 1 || isNaN(data30)){
const err77 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err77];
}
else {
vErrors.push(err77);
}
errors++;
}
if(data30 < 0 || isNaN(data30)){
const err78 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err78];
}
else {
vErrors.push(err78);
}
errors++;
}
}
else {
const err79 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err79];
}
else {
vErrors.push(err79);
}
errors++;
}
}
}
else {
const err80 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err80];
}
else {
vErrors.push(err80);
}
errors++;
}
}
if(data23.layout !== undefined){
let data31 = data23.layout;
if(data31 && typeof data31 == "object" && !Array.isArray(data31)){
if(data31.x === undefined){
const err81 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err81];
}
else {
vErrors.push(err81);
}
errors++;
}
if(data31.y === undefined){
const err82 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err82];
}
else {
vErrors.push(err82);
}
errors++;
}
if(data31.width === undefined){
const err83 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err83];
}
else {
vErrors.push(err83);
}
errors++;
}
if(data31.height === undefined){
const err84 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err84];
}
else {
vErrors.push(err84);
}
errors++;
}
for(const key6 in data31){
if(!((((key6 === "x") || (key6 === "y")) || (key6 === "width")) || (key6 === "height"))){
const err85 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key6},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err85];
}
else {
vErrors.push(err85);
}
errors++;
}
}
if(data31.x !== undefined){
let data32 = data31.x;
if(typeof data32 == "number"){
if(data32 > 1 || isNaN(data32)){
const err86 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/x/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err86];
}
else {
vErrors.push(err86);
}
errors++;
}
if(data32 < 0 || isNaN(data32)){
const err87 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/x/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err87];
}
else {
vErrors.push(err87);
}
errors++;
}
}
else {
const err88 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err88];
}
else {
vErrors.push(err88);
}
errors++;
}
}
if(data31.y !== undefined){
let data33 = data31.y;
if(typeof data33 == "number"){
if(data33 > 1 || isNaN(data33)){
const err89 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/y/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err89];
}
else {
vErrors.push(err89);
}
errors++;
}
if(data33 < 0 || isNaN(data33)){
const err90 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/y/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err90];
}
else {
vErrors.push(err90);
}
errors++;
}
}
else {
const err91 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err91];
}
else {
vErrors.push(err91);
}
errors++;
}
}
if(data31.width !== undefined){
let data34 = data31.width;
if(typeof data34 == "number"){
if(data34 > 1 || isNaN(data34)){
const err92 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err92];
}
else {
vErrors.push(err92);
}
errors++;
}
if(data34 < 0 || isNaN(data34)){
const err93 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err93];
}
else {
vErrors.push(err93);
}
errors++;
}
if(data34 <= 0 || isNaN(data34)){
const err94 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err94];
}
else {
vErrors.push(err94);
}
errors++;
}
}
else {
const err95 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err95];
}
else {
vErrors.push(err95);
}
errors++;
}
}
if(data31.height !== undefined){
let data35 = data31.height;
if(typeof data35 == "number"){
if(data35 > 1 || isNaN(data35)){
const err96 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/height/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err96];
}
else {
vErrors.push(err96);
}
errors++;
}
if(data35 < 0 || isNaN(data35)){
const err97 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/height/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err97];
}
else {
vErrors.push(err97);
}
errors++;
}
if(data35 <= 0 || isNaN(data35)){
const err98 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err98];
}
else {
vErrors.push(err98);
}
errors++;
}
}
else {
const err99 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err99];
}
else {
vErrors.push(err99);
}
errors++;
}
}
}
else {
const err100 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/properties/layout/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err100];
}
else {
vErrors.push(err100);
}
errors++;
}
}
}
else {
const err101 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/0/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err101];
}
else {
vErrors.push(err101);
}
errors++;
}
var _valid0 = _errs49 === errors;
if(_valid0){
valid12 = true;
passing0 = 0;
var props0 = true;
}
const _errs76 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err102 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err102];
}
else {
vErrors.push(err102);
}
errors++;
}
if(data23.element_id === undefined){
const err103 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err103];
}
else {
vErrors.push(err103);
}
errors++;
}
if(data23.slot === undefined){
const err104 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/required",keyword:"required",params:{missingProperty: "slot"},message:"must have required property '"+"slot"+"'"};
if(vErrors === null){
vErrors = [err104];
}
else {
vErrors.push(err104);
}
errors++;
}
if(data23.latex === undefined){
const err105 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/required",keyword:"required",params:{missingProperty: "latex"},message:"must have required property '"+"latex"+"'"};
if(vErrors === null){
vErrors = [err105];
}
else {
vErrors.push(err105);
}
errors++;
}
for(const key7 in data23){
if(!((((((key7 === "type") || (key7 === "element_id")) || (key7 === "slot")) || (key7 === "latex")) || (key7 === "timing")) || (key7 === "layout"))){
const err106 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key7},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err106];
}
else {
vErrors.push(err106);
}
errors++;
}
}
if(data23.type !== undefined){
if("equation" !== data23.type){
const err107 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/type/const",keyword:"const",params:{allowedValue: "equation"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err107];
}
else {
vErrors.push(err107);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data37 = data23.element_id;
if(typeof data37 === "string"){
if(func2(data37) < 1){
const err108 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err108];
}
else {
vErrors.push(err108);
}
errors++;
}
}
else {
const err109 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err109];
}
else {
vErrors.push(err109);
}
errors++;
}
}
if(data23.slot !== undefined){
let data38 = data23.slot;
if(!(((((data38 === "main") || (data38 === "left")) || (data38 === "right")) || (data38 === "bottom")) || (data38 === "overlay"))){
const err110 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[1].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err110];
}
else {
vErrors.push(err110);
}
errors++;
}
}
if(data23.latex !== undefined){
let data39 = data23.latex;
if(typeof data39 === "string"){
if(func2(data39) < 1){
const err111 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/latex",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/latex/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err111];
}
else {
vErrors.push(err111);
}
errors++;
}
}
else {
const err112 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/latex",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/latex/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err112];
}
else {
vErrors.push(err112);
}
errors++;
}
}
if(data23.timing !== undefined){
let data40 = data23.timing;
if(data40 && typeof data40 == "object" && !Array.isArray(data40)){
if(data40.start === undefined){
const err113 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err113];
}
else {
vErrors.push(err113);
}
errors++;
}
if(data40.end === undefined){
const err114 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err114];
}
else {
vErrors.push(err114);
}
errors++;
}
for(const key8 in data40){
if(!((key8 === "start") || (key8 === "end"))){
const err115 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key8},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err115];
}
else {
vErrors.push(err115);
}
errors++;
}
}
if(data40.start !== undefined){
let data41 = data40.start;
if(typeof data41 == "number"){
if(data41 > 1 || isNaN(data41)){
const err116 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err116];
}
else {
vErrors.push(err116);
}
errors++;
}
if(data41 < 0 || isNaN(data41)){
const err117 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err117];
}
else {
vErrors.push(err117);
}
errors++;
}
}
else {
const err118 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err118];
}
else {
vErrors.push(err118);
}
errors++;
}
}
if(data40.end !== undefined){
let data42 = data40.end;
if(typeof data42 == "number"){
if(data42 > 1 || isNaN(data42)){
const err119 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err119];
}
else {
vErrors.push(err119);
}
errors++;
}
if(data42 < 0 || isNaN(data42)){
const err120 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err120];
}
else {
vErrors.push(err120);
}
errors++;
}
}
else {
const err121 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err121];
}
else {
vErrors.push(err121);
}
errors++;
}
}
}
else {
const err122 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err122];
}
else {
vErrors.push(err122);
}
errors++;
}
}
if(data23.layout !== undefined){
let data43 = data23.layout;
if(data43 && typeof data43 == "object" && !Array.isArray(data43)){
if(data43.x === undefined){
const err123 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err123];
}
else {
vErrors.push(err123);
}
errors++;
}
if(data43.y === undefined){
const err124 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err124];
}
else {
vErrors.push(err124);
}
errors++;
}
if(data43.width === undefined){
const err125 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err125];
}
else {
vErrors.push(err125);
}
errors++;
}
if(data43.height === undefined){
const err126 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err126];
}
else {
vErrors.push(err126);
}
errors++;
}
for(const key9 in data43){
if(!((((key9 === "x") || (key9 === "y")) || (key9 === "width")) || (key9 === "height"))){
const err127 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key9},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err127];
}
else {
vErrors.push(err127);
}
errors++;
}
}
if(data43.x !== undefined){
let data44 = data43.x;
if(typeof data44 == "number"){
if(data44 > 1 || isNaN(data44)){
const err128 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/x/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err128];
}
else {
vErrors.push(err128);
}
errors++;
}
if(data44 < 0 || isNaN(data44)){
const err129 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/x/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err129];
}
else {
vErrors.push(err129);
}
errors++;
}
}
else {
const err130 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err130];
}
else {
vErrors.push(err130);
}
errors++;
}
}
if(data43.y !== undefined){
let data45 = data43.y;
if(typeof data45 == "number"){
if(data45 > 1 || isNaN(data45)){
const err131 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/y/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err131];
}
else {
vErrors.push(err131);
}
errors++;
}
if(data45 < 0 || isNaN(data45)){
const err132 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/y/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err132];
}
else {
vErrors.push(err132);
}
errors++;
}
}
else {
const err133 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err133];
}
else {
vErrors.push(err133);
}
errors++;
}
}
if(data43.width !== undefined){
let data46 = data43.width;
if(typeof data46 == "number"){
if(data46 > 1 || isNaN(data46)){
const err134 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err134];
}
else {
vErrors.push(err134);
}
errors++;
}
if(data46 < 0 || isNaN(data46)){
const err135 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err135];
}
else {
vErrors.push(err135);
}
errors++;
}
if(data46 <= 0 || isNaN(data46)){
const err136 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err136];
}
else {
vErrors.push(err136);
}
errors++;
}
}
else {
const err137 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err137];
}
else {
vErrors.push(err137);
}
errors++;
}
}
if(data43.height !== undefined){
let data47 = data43.height;
if(typeof data47 == "number"){
if(data47 > 1 || isNaN(data47)){
const err138 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/height/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err138];
}
else {
vErrors.push(err138);
}
errors++;
}
if(data47 < 0 || isNaN(data47)){
const err139 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/height/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err139];
}
else {
vErrors.push(err139);
}
errors++;
}
if(data47 <= 0 || isNaN(data47)){
const err140 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err140];
}
else {
vErrors.push(err140);
}
errors++;
}
}
else {
const err141 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err141];
}
else {
vErrors.push(err141);
}
errors++;
}
}
}
else {
const err142 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/properties/layout/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err142];
}
else {
vErrors.push(err142);
}
errors++;
}
}
}
else {
const err143 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/1/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err143];
}
else {
vErrors.push(err143);
}
errors++;
}
var _valid0 = _errs76 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 1];
}
else {
if(_valid0){
valid12 = true;
passing0 = 1;
if(props0 !== true){
props0 = true;
}
}
const _errs103 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err144 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err144];
}
else {
vErrors.push(err144);
}
errors++;
}
if(data23.element_id === undefined){
const err145 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err145];
}
else {
vErrors.push(err145);
}
errors++;
}
if(data23.slot === undefined){
const err146 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/required",keyword:"required",params:{missingProperty: "slot"},message:"must have required property '"+"slot"+"'"};
if(vErrors === null){
vErrors = [err146];
}
else {
vErrors.push(err146);
}
errors++;
}
if(data23.columns === undefined){
const err147 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/required",keyword:"required",params:{missingProperty: "columns"},message:"must have required property '"+"columns"+"'"};
if(vErrors === null){
vErrors = [err147];
}
else {
vErrors.push(err147);
}
errors++;
}
if(data23.rows === undefined){
const err148 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/required",keyword:"required",params:{missingProperty: "rows"},message:"must have required property '"+"rows"+"'"};
if(vErrors === null){
vErrors = [err148];
}
else {
vErrors.push(err148);
}
errors++;
}
for(const key10 in data23){
if(!(func1.call(schema31.properties.steps.items.properties.board_actions.items.oneOf[2].properties, key10))){
const err149 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key10},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err149];
}
else {
vErrors.push(err149);
}
errors++;
}
}
if(data23.type !== undefined){
if("table" !== data23.type){
const err150 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/type/const",keyword:"const",params:{allowedValue: "table"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err150];
}
else {
vErrors.push(err150);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data49 = data23.element_id;
if(typeof data49 === "string"){
if(func2(data49) < 1){
const err151 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err151];
}
else {
vErrors.push(err151);
}
errors++;
}
}
else {
const err152 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err152];
}
else {
vErrors.push(err152);
}
errors++;
}
}
if(data23.slot !== undefined){
let data50 = data23.slot;
if(!(((((data50 === "main") || (data50 === "left")) || (data50 === "right")) || (data50 === "bottom")) || (data50 === "overlay"))){
const err153 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[2].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err153];
}
else {
vErrors.push(err153);
}
errors++;
}
}
if(data23.columns !== undefined){
let data51 = data23.columns;
if(Array.isArray(data51)){
if(data51.length > 50){
const err154 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/columns",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/columns/maxItems",keyword:"maxItems",params:{limit: 50},message:"must NOT have more than 50 items"};
if(vErrors === null){
vErrors = [err154];
}
else {
vErrors.push(err154);
}
errors++;
}
if(data51.length < 1){
const err155 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/columns",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/columns/minItems",keyword:"minItems",params:{limit: 1},message:"must NOT have fewer than 1 items"};
if(vErrors === null){
vErrors = [err155];
}
else {
vErrors.push(err155);
}
errors++;
}
const len4 = data51.length;
for(let i4=0; i4<len4; i4++){
if(typeof data51[i4] !== "string"){
const err156 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/columns/" + i4,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/columns/items/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err156];
}
else {
vErrors.push(err156);
}
errors++;
}
}
}
else {
const err157 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/columns",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/columns/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err157];
}
else {
vErrors.push(err157);
}
errors++;
}
}
if(data23.rows !== undefined){
let data53 = data23.rows;
if(Array.isArray(data53)){
if(data53.length > 200){
const err158 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/rows",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/rows/maxItems",keyword:"maxItems",params:{limit: 200},message:"must NOT have more than 200 items"};
if(vErrors === null){
vErrors = [err158];
}
else {
vErrors.push(err158);
}
errors++;
}
const len5 = data53.length;
for(let i5=0; i5<len5; i5++){
let data54 = data53[i5];
if(Array.isArray(data54)){
const len6 = data54.length;
for(let i6=0; i6<len6; i6++){
let data55 = data54[i6];
if((((typeof data55 !== "string") && (!(typeof data55 == "number"))) && (typeof data55 !== "boolean")) && (data55 !== null)){
const err159 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/rows/" + i5+"/" + i6,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/rows/items/items/type",keyword:"type",params:{type: schema31.properties.steps.items.properties.board_actions.items.oneOf[2].properties.rows.items.items.type},message:"must be string,number,boolean,null"};
if(vErrors === null){
vErrors = [err159];
}
else {
vErrors.push(err159);
}
errors++;
}
}
}
else {
const err160 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/rows/" + i5,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/rows/items/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err160];
}
else {
vErrors.push(err160);
}
errors++;
}
}
}
else {
const err161 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/rows",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/rows/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err161];
}
else {
vErrors.push(err161);
}
errors++;
}
}
if(data23.caption !== undefined){
if(typeof data23.caption !== "string"){
const err162 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/caption",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/caption/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err162];
}
else {
vErrors.push(err162);
}
errors++;
}
}
if(data23.timing !== undefined){
let data57 = data23.timing;
if(data57 && typeof data57 == "object" && !Array.isArray(data57)){
if(data57.start === undefined){
const err163 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err163];
}
else {
vErrors.push(err163);
}
errors++;
}
if(data57.end === undefined){
const err164 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err164];
}
else {
vErrors.push(err164);
}
errors++;
}
for(const key11 in data57){
if(!((key11 === "start") || (key11 === "end"))){
const err165 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key11},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err165];
}
else {
vErrors.push(err165);
}
errors++;
}
}
if(data57.start !== undefined){
let data58 = data57.start;
if(typeof data58 == "number"){
if(data58 > 1 || isNaN(data58)){
const err166 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err166];
}
else {
vErrors.push(err166);
}
errors++;
}
if(data58 < 0 || isNaN(data58)){
const err167 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err167];
}
else {
vErrors.push(err167);
}
errors++;
}
}
else {
const err168 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err168];
}
else {
vErrors.push(err168);
}
errors++;
}
}
if(data57.end !== undefined){
let data59 = data57.end;
if(typeof data59 == "number"){
if(data59 > 1 || isNaN(data59)){
const err169 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err169];
}
else {
vErrors.push(err169);
}
errors++;
}
if(data59 < 0 || isNaN(data59)){
const err170 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err170];
}
else {
vErrors.push(err170);
}
errors++;
}
}
else {
const err171 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err171];
}
else {
vErrors.push(err171);
}
errors++;
}
}
}
else {
const err172 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err172];
}
else {
vErrors.push(err172);
}
errors++;
}
}
if(data23.layout !== undefined){
let data60 = data23.layout;
if(data60 && typeof data60 == "object" && !Array.isArray(data60)){
if(data60.x === undefined){
const err173 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err173];
}
else {
vErrors.push(err173);
}
errors++;
}
if(data60.y === undefined){
const err174 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err174];
}
else {
vErrors.push(err174);
}
errors++;
}
if(data60.width === undefined){
const err175 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err175];
}
else {
vErrors.push(err175);
}
errors++;
}
if(data60.height === undefined){
const err176 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err176];
}
else {
vErrors.push(err176);
}
errors++;
}
for(const key12 in data60){
if(!((((key12 === "x") || (key12 === "y")) || (key12 === "width")) || (key12 === "height"))){
const err177 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key12},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err177];
}
else {
vErrors.push(err177);
}
errors++;
}
}
if(data60.x !== undefined){
let data61 = data60.x;
if(typeof data61 == "number"){
if(data61 > 1 || isNaN(data61)){
const err178 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/x/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err178];
}
else {
vErrors.push(err178);
}
errors++;
}
if(data61 < 0 || isNaN(data61)){
const err179 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/x/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err179];
}
else {
vErrors.push(err179);
}
errors++;
}
}
else {
const err180 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err180];
}
else {
vErrors.push(err180);
}
errors++;
}
}
if(data60.y !== undefined){
let data62 = data60.y;
if(typeof data62 == "number"){
if(data62 > 1 || isNaN(data62)){
const err181 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/y/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err181];
}
else {
vErrors.push(err181);
}
errors++;
}
if(data62 < 0 || isNaN(data62)){
const err182 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/y/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err182];
}
else {
vErrors.push(err182);
}
errors++;
}
}
else {
const err183 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err183];
}
else {
vErrors.push(err183);
}
errors++;
}
}
if(data60.width !== undefined){
let data63 = data60.width;
if(typeof data63 == "number"){
if(data63 > 1 || isNaN(data63)){
const err184 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err184];
}
else {
vErrors.push(err184);
}
errors++;
}
if(data63 < 0 || isNaN(data63)){
const err185 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err185];
}
else {
vErrors.push(err185);
}
errors++;
}
if(data63 <= 0 || isNaN(data63)){
const err186 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err186];
}
else {
vErrors.push(err186);
}
errors++;
}
}
else {
const err187 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err187];
}
else {
vErrors.push(err187);
}
errors++;
}
}
if(data60.height !== undefined){
let data64 = data60.height;
if(typeof data64 == "number"){
if(data64 > 1 || isNaN(data64)){
const err188 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/height/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err188];
}
else {
vErrors.push(err188);
}
errors++;
}
if(data64 < 0 || isNaN(data64)){
const err189 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/height/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err189];
}
else {
vErrors.push(err189);
}
errors++;
}
if(data64 <= 0 || isNaN(data64)){
const err190 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err190];
}
else {
vErrors.push(err190);
}
errors++;
}
}
else {
const err191 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err191];
}
else {
vErrors.push(err191);
}
errors++;
}
}
}
else {
const err192 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/layout/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err192];
}
else {
vErrors.push(err192);
}
errors++;
}
}
if(data23.row_ids !== undefined){
let data65 = data23.row_ids;
if(Array.isArray(data65)){
if(data65.length > 200){
const err193 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/row_ids/maxItems",keyword:"maxItems",params:{limit: 200},message:"must NOT have more than 200 items"};
if(vErrors === null){
vErrors = [err193];
}
else {
vErrors.push(err193);
}
errors++;
}
const len7 = data65.length;
for(let i7=0; i7<len7; i7++){
let data66 = data65[i7];
if(typeof data66 === "string"){
if(func2(data66) > 200){
const err194 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_ids/" + i7,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/row_ids/items/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err194];
}
else {
vErrors.push(err194);
}
errors++;
}
if(func2(data66) < 1){
const err195 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_ids/" + i7,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/row_ids/items/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err195];
}
else {
vErrors.push(err195);
}
errors++;
}
}
else {
const err196 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_ids/" + i7,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/row_ids/items/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err196];
}
else {
vErrors.push(err196);
}
errors++;
}
}
let i8 = data65.length;
let j0;
if(i8 > 1){
const indices0 = {};
for(;i8--;){
let item0 = data65[i8];
if(typeof item0 !== "string"){
continue;
}
if(typeof indices0[item0] == "number"){
j0 = indices0[item0];
const err197 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/row_ids/uniqueItems",keyword:"uniqueItems",params:{i: i8, j: j0},message:"must NOT have duplicate items (items ## "+j0+" and "+i8+" are identical)"};
if(vErrors === null){
vErrors = [err197];
}
else {
vErrors.push(err197);
}
errors++;
break;
}
indices0[item0] = i8;
}
}
}
else {
const err198 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/row_ids/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err198];
}
else {
vErrors.push(err198);
}
errors++;
}
}
if(data23.column_ids !== undefined){
let data67 = data23.column_ids;
if(Array.isArray(data67)){
if(data67.length > 50){
const err199 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/column_ids/maxItems",keyword:"maxItems",params:{limit: 50},message:"must NOT have more than 50 items"};
if(vErrors === null){
vErrors = [err199];
}
else {
vErrors.push(err199);
}
errors++;
}
const len8 = data67.length;
for(let i9=0; i9<len8; i9++){
let data68 = data67[i9];
if(typeof data68 === "string"){
if(func2(data68) > 200){
const err200 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_ids/" + i9,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/column_ids/items/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err200];
}
else {
vErrors.push(err200);
}
errors++;
}
if(func2(data68) < 1){
const err201 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_ids/" + i9,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/column_ids/items/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err201];
}
else {
vErrors.push(err201);
}
errors++;
}
}
else {
const err202 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_ids/" + i9,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/column_ids/items/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err202];
}
else {
vErrors.push(err202);
}
errors++;
}
}
let i10 = data67.length;
let j1;
if(i10 > 1){
const indices1 = {};
for(;i10--;){
let item1 = data67[i10];
if(typeof item1 !== "string"){
continue;
}
if(typeof indices1[item1] == "number"){
j1 = indices1[item1];
const err203 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/column_ids/uniqueItems",keyword:"uniqueItems",params:{i: i10, j: j1},message:"must NOT have duplicate items (items ## "+j1+" and "+i10+" are identical)"};
if(vErrors === null){
vErrors = [err203];
}
else {
vErrors.push(err203);
}
errors++;
break;
}
indices1[item1] = i10;
}
}
}
else {
const err204 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/column_ids/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err204];
}
else {
vErrors.push(err204);
}
errors++;
}
}
if(data23.cell_ids !== undefined){
let data69 = data23.cell_ids;
if(Array.isArray(data69)){
if(data69.length > 200){
const err205 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/maxItems",keyword:"maxItems",params:{limit: 200},message:"must NOT have more than 200 items"};
if(vErrors === null){
vErrors = [err205];
}
else {
vErrors.push(err205);
}
errors++;
}
const len9 = data69.length;
for(let i11=0; i11<len9; i11++){
let data70 = data69[i11];
if(Array.isArray(data70)){
if(data70.length > 50){
const err206 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i11,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/items/maxItems",keyword:"maxItems",params:{limit: 50},message:"must NOT have more than 50 items"};
if(vErrors === null){
vErrors = [err206];
}
else {
vErrors.push(err206);
}
errors++;
}
const len10 = data70.length;
for(let i12=0; i12<len10; i12++){
let data71 = data70[i12];
if(typeof data71 === "string"){
if(func2(data71) > 200){
const err207 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i11+"/" + i12,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/items/items/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err207];
}
else {
vErrors.push(err207);
}
errors++;
}
if(func2(data71) < 1){
const err208 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i11+"/" + i12,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/items/items/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err208];
}
else {
vErrors.push(err208);
}
errors++;
}
}
else {
const err209 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i11+"/" + i12,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/items/items/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err209];
}
else {
vErrors.push(err209);
}
errors++;
}
}
let i13 = data70.length;
let j2;
if(i13 > 1){
const indices2 = {};
for(;i13--;){
let item2 = data70[i13];
if(typeof item2 !== "string"){
continue;
}
if(typeof indices2[item2] == "number"){
j2 = indices2[item2];
const err210 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i11,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/items/uniqueItems",keyword:"uniqueItems",params:{i: i13, j: j2},message:"must NOT have duplicate items (items ## "+j2+" and "+i13+" are identical)"};
if(vErrors === null){
vErrors = [err210];
}
else {
vErrors.push(err210);
}
errors++;
break;
}
indices2[item2] = i13;
}
}
}
else {
const err211 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i11,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/items/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err211];
}
else {
vErrors.push(err211);
}
errors++;
}
}
}
else {
const err212 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/cell_ids/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err212];
}
else {
vErrors.push(err212);
}
errors++;
}
}
if(data23.table_name !== undefined){
let data72 = data23.table_name;
if(typeof data72 === "string"){
if(func2(data72) > 200){
const err213 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/table_name",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/table_name/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err213];
}
else {
vErrors.push(err213);
}
errors++;
}
if(func2(data72) < 1){
const err214 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/table_name",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/table_name/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err214];
}
else {
vErrors.push(err214);
}
errors++;
}
}
else {
const err215 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/table_name",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/properties/table_name/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err215];
}
else {
vErrors.push(err215);
}
errors++;
}
}
}
else {
const err216 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/2/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err216];
}
else {
vErrors.push(err216);
}
errors++;
}
var _valid0 = _errs103 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 2];
}
else {
if(_valid0){
valid12 = true;
passing0 = 2;
if(props0 !== true){
props0 = true;
}
}
const _errs156 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err217 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err217];
}
else {
vErrors.push(err217);
}
errors++;
}
if(data23.element_id === undefined){
const err218 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err218];
}
else {
vErrors.push(err218);
}
errors++;
}
if(data23.slot === undefined){
const err219 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/required",keyword:"required",params:{missingProperty: "slot"},message:"must have required property '"+"slot"+"'"};
if(vErrors === null){
vErrors = [err219];
}
else {
vErrors.push(err219);
}
errors++;
}
if(data23.language === undefined){
const err220 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/required",keyword:"required",params:{missingProperty: "language"},message:"must have required property '"+"language"+"'"};
if(vErrors === null){
vErrors = [err220];
}
else {
vErrors.push(err220);
}
errors++;
}
if(data23.code === undefined){
const err221 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/required",keyword:"required",params:{missingProperty: "code"},message:"must have required property '"+"code"+"'"};
if(vErrors === null){
vErrors = [err221];
}
else {
vErrors.push(err221);
}
errors++;
}
for(const key13 in data23){
if(!(((((((key13 === "type") || (key13 === "element_id")) || (key13 === "slot")) || (key13 === "language")) || (key13 === "code")) || (key13 === "timing")) || (key13 === "layout"))){
const err222 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key13},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err222];
}
else {
vErrors.push(err222);
}
errors++;
}
}
if(data23.type !== undefined){
if("code" !== data23.type){
const err223 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/type/const",keyword:"const",params:{allowedValue: "code"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err223];
}
else {
vErrors.push(err223);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data74 = data23.element_id;
if(typeof data74 === "string"){
if(func2(data74) < 1){
const err224 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err224];
}
else {
vErrors.push(err224);
}
errors++;
}
}
else {
const err225 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err225];
}
else {
vErrors.push(err225);
}
errors++;
}
}
if(data23.slot !== undefined){
let data75 = data23.slot;
if(!(((((data75 === "main") || (data75 === "left")) || (data75 === "right")) || (data75 === "bottom")) || (data75 === "overlay"))){
const err226 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[3].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err226];
}
else {
vErrors.push(err226);
}
errors++;
}
}
if(data23.language !== undefined){
let data76 = data23.language;
if(!(((((data76 === "sql") || (data76 === "python")) || (data76 === "java")) || (data76 === "c")) || (data76 === "text"))){
const err227 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/language",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/language/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[3].properties.language.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err227];
}
else {
vErrors.push(err227);
}
errors++;
}
}
if(data23.code !== undefined){
let data77 = data23.code;
if(typeof data77 === "string"){
if(func2(data77) < 1){
const err228 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/code",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/code/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err228];
}
else {
vErrors.push(err228);
}
errors++;
}
}
else {
const err229 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/code",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/code/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err229];
}
else {
vErrors.push(err229);
}
errors++;
}
}
if(data23.timing !== undefined){
let data78 = data23.timing;
if(data78 && typeof data78 == "object" && !Array.isArray(data78)){
if(data78.start === undefined){
const err230 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err230];
}
else {
vErrors.push(err230);
}
errors++;
}
if(data78.end === undefined){
const err231 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err231];
}
else {
vErrors.push(err231);
}
errors++;
}
for(const key14 in data78){
if(!((key14 === "start") || (key14 === "end"))){
const err232 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key14},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err232];
}
else {
vErrors.push(err232);
}
errors++;
}
}
if(data78.start !== undefined){
let data79 = data78.start;
if(typeof data79 == "number"){
if(data79 > 1 || isNaN(data79)){
const err233 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err233];
}
else {
vErrors.push(err233);
}
errors++;
}
if(data79 < 0 || isNaN(data79)){
const err234 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err234];
}
else {
vErrors.push(err234);
}
errors++;
}
}
else {
const err235 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err235];
}
else {
vErrors.push(err235);
}
errors++;
}
}
if(data78.end !== undefined){
let data80 = data78.end;
if(typeof data80 == "number"){
if(data80 > 1 || isNaN(data80)){
const err236 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err236];
}
else {
vErrors.push(err236);
}
errors++;
}
if(data80 < 0 || isNaN(data80)){
const err237 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err237];
}
else {
vErrors.push(err237);
}
errors++;
}
}
else {
const err238 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err238];
}
else {
vErrors.push(err238);
}
errors++;
}
}
}
else {
const err239 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err239];
}
else {
vErrors.push(err239);
}
errors++;
}
}
if(data23.layout !== undefined){
let data81 = data23.layout;
if(data81 && typeof data81 == "object" && !Array.isArray(data81)){
if(data81.x === undefined){
const err240 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err240];
}
else {
vErrors.push(err240);
}
errors++;
}
if(data81.y === undefined){
const err241 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err241];
}
else {
vErrors.push(err241);
}
errors++;
}
if(data81.width === undefined){
const err242 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err242];
}
else {
vErrors.push(err242);
}
errors++;
}
if(data81.height === undefined){
const err243 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err243];
}
else {
vErrors.push(err243);
}
errors++;
}
for(const key15 in data81){
if(!((((key15 === "x") || (key15 === "y")) || (key15 === "width")) || (key15 === "height"))){
const err244 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key15},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err244];
}
else {
vErrors.push(err244);
}
errors++;
}
}
if(data81.x !== undefined){
let data82 = data81.x;
if(typeof data82 == "number"){
if(data82 > 1 || isNaN(data82)){
const err245 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/x/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err245];
}
else {
vErrors.push(err245);
}
errors++;
}
if(data82 < 0 || isNaN(data82)){
const err246 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/x/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err246];
}
else {
vErrors.push(err246);
}
errors++;
}
}
else {
const err247 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err247];
}
else {
vErrors.push(err247);
}
errors++;
}
}
if(data81.y !== undefined){
let data83 = data81.y;
if(typeof data83 == "number"){
if(data83 > 1 || isNaN(data83)){
const err248 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/y/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err248];
}
else {
vErrors.push(err248);
}
errors++;
}
if(data83 < 0 || isNaN(data83)){
const err249 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/y/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err249];
}
else {
vErrors.push(err249);
}
errors++;
}
}
else {
const err250 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err250];
}
else {
vErrors.push(err250);
}
errors++;
}
}
if(data81.width !== undefined){
let data84 = data81.width;
if(typeof data84 == "number"){
if(data84 > 1 || isNaN(data84)){
const err251 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err251];
}
else {
vErrors.push(err251);
}
errors++;
}
if(data84 < 0 || isNaN(data84)){
const err252 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err252];
}
else {
vErrors.push(err252);
}
errors++;
}
if(data84 <= 0 || isNaN(data84)){
const err253 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err253];
}
else {
vErrors.push(err253);
}
errors++;
}
}
else {
const err254 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err254];
}
else {
vErrors.push(err254);
}
errors++;
}
}
if(data81.height !== undefined){
let data85 = data81.height;
if(typeof data85 == "number"){
if(data85 > 1 || isNaN(data85)){
const err255 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/height/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err255];
}
else {
vErrors.push(err255);
}
errors++;
}
if(data85 < 0 || isNaN(data85)){
const err256 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/height/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err256];
}
else {
vErrors.push(err256);
}
errors++;
}
if(data85 <= 0 || isNaN(data85)){
const err257 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err257];
}
else {
vErrors.push(err257);
}
errors++;
}
}
else {
const err258 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err258];
}
else {
vErrors.push(err258);
}
errors++;
}
}
}
else {
const err259 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/layout",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/properties/layout/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err259];
}
else {
vErrors.push(err259);
}
errors++;
}
}
}
else {
const err260 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/3/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err260];
}
else {
vErrors.push(err260);
}
errors++;
}
var _valid0 = _errs156 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 3];
}
else {
if(_valid0){
valid12 = true;
passing0 = 3;
if(props0 !== true){
props0 = true;
}
}
const _errs184 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err261 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err261];
}
else {
vErrors.push(err261);
}
errors++;
}
if(data23.target_element_id === undefined){
const err262 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/required",keyword:"required",params:{missingProperty: "target_element_id"},message:"must have required property '"+"target_element_id"+"'"};
if(vErrors === null){
vErrors = [err262];
}
else {
vErrors.push(err262);
}
errors++;
}
if(data23.style === undefined){
const err263 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/required",keyword:"required",params:{missingProperty: "style"},message:"must have required property '"+"style"+"'"};
if(vErrors === null){
vErrors = [err263];
}
else {
vErrors.push(err263);
}
errors++;
}
for(const key16 in data23){
if(!(func1.call(schema31.properties.steps.items.properties.board_actions.items.oneOf[4].properties, key16))){
const err264 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key16},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err264];
}
else {
vErrors.push(err264);
}
errors++;
}
}
if(data23.type !== undefined){
if("highlight" !== data23.type){
const err265 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/type/const",keyword:"const",params:{allowedValue: "highlight"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err265];
}
else {
vErrors.push(err265);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data87 = data23.element_id;
if(typeof data87 === "string"){
if(func2(data87) < 1){
const err266 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err266];
}
else {
vErrors.push(err266);
}
errors++;
}
}
else {
const err267 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err267];
}
else {
vErrors.push(err267);
}
errors++;
}
}
if(data23.slot !== undefined){
let data88 = data23.slot;
if(!(((((data88 === "main") || (data88 === "left")) || (data88 === "right")) || (data88 === "bottom")) || (data88 === "overlay"))){
const err268 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[4].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err268];
}
else {
vErrors.push(err268);
}
errors++;
}
}
if(data23.target_element_id !== undefined){
let data89 = data23.target_element_id;
if(typeof data89 === "string"){
if(func2(data89) < 1){
const err269 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/target_element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/target_element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err269];
}
else {
vErrors.push(err269);
}
errors++;
}
}
else {
const err270 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/target_element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/target_element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err270];
}
else {
vErrors.push(err270);
}
errors++;
}
}
if(data23.row_indices !== undefined){
let data90 = data23.row_indices;
if(Array.isArray(data90)){
const len11 = data90.length;
for(let i14=0; i14<len11; i14++){
let data91 = data90[i14];
if(!((typeof data91 == "number") && (!(data91 % 1) && !isNaN(data91)))){
const err271 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_indices/" + i14,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/row_indices/items/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err271];
}
else {
vErrors.push(err271);
}
errors++;
}
if(typeof data91 == "number"){
if(data91 < 0 || isNaN(data91)){
const err272 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_indices/" + i14,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/row_indices/items/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err272];
}
else {
vErrors.push(err272);
}
errors++;
}
}
}
}
else {
const err273 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/row_indices",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/row_indices/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err273];
}
else {
vErrors.push(err273);
}
errors++;
}
}
if(data23.column_indices !== undefined){
let data92 = data23.column_indices;
if(Array.isArray(data92)){
const len12 = data92.length;
for(let i15=0; i15<len12; i15++){
let data93 = data92[i15];
if(!((typeof data93 == "number") && (!(data93 % 1) && !isNaN(data93)))){
const err274 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_indices/" + i15,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/column_indices/items/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err274];
}
else {
vErrors.push(err274);
}
errors++;
}
if(typeof data93 == "number"){
if(data93 < 0 || isNaN(data93)){
const err275 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_indices/" + i15,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/column_indices/items/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err275];
}
else {
vErrors.push(err275);
}
errors++;
}
}
}
}
else {
const err276 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/column_indices",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/column_indices/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err276];
}
else {
vErrors.push(err276);
}
errors++;
}
}
if(data23.style !== undefined){
let data94 = data23.style;
if(!(((data94 === "outline") || (data94 === "underline")) || (data94 === "background"))){
const err277 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/style",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/style/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[4].properties.style.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err277];
}
else {
vErrors.push(err277);
}
errors++;
}
}
if(data23.timing !== undefined){
let data95 = data23.timing;
if(data95 && typeof data95 == "object" && !Array.isArray(data95)){
if(data95.start === undefined){
const err278 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err278];
}
else {
vErrors.push(err278);
}
errors++;
}
if(data95.end === undefined){
const err279 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err279];
}
else {
vErrors.push(err279);
}
errors++;
}
for(const key17 in data95){
if(!((key17 === "start") || (key17 === "end"))){
const err280 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key17},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err280];
}
else {
vErrors.push(err280);
}
errors++;
}
}
if(data95.start !== undefined){
let data96 = data95.start;
if(typeof data96 == "number"){
if(data96 > 1 || isNaN(data96)){
const err281 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err281];
}
else {
vErrors.push(err281);
}
errors++;
}
if(data96 < 0 || isNaN(data96)){
const err282 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err282];
}
else {
vErrors.push(err282);
}
errors++;
}
}
else {
const err283 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err283];
}
else {
vErrors.push(err283);
}
errors++;
}
}
if(data95.end !== undefined){
let data97 = data95.end;
if(typeof data97 == "number"){
if(data97 > 1 || isNaN(data97)){
const err284 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err284];
}
else {
vErrors.push(err284);
}
errors++;
}
if(data97 < 0 || isNaN(data97)){
const err285 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err285];
}
else {
vErrors.push(err285);
}
errors++;
}
}
else {
const err286 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err286];
}
else {
vErrors.push(err286);
}
errors++;
}
}
}
else {
const err287 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err287];
}
else {
vErrors.push(err287);
}
errors++;
}
}
if(data23.cell_ids !== undefined){
let data98 = data23.cell_ids;
if(Array.isArray(data98)){
if(data98.length > 500){
const err288 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/cell_ids/maxItems",keyword:"maxItems",params:{limit: 500},message:"must NOT have more than 500 items"};
if(vErrors === null){
vErrors = [err288];
}
else {
vErrors.push(err288);
}
errors++;
}
const len13 = data98.length;
for(let i16=0; i16<len13; i16++){
let data99 = data98[i16];
if(typeof data99 === "string"){
if(func2(data99) > 200){
const err289 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i16,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/cell_ids/items/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err289];
}
else {
vErrors.push(err289);
}
errors++;
}
if(func2(data99) < 1){
const err290 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i16,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/cell_ids/items/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err290];
}
else {
vErrors.push(err290);
}
errors++;
}
}
else {
const err291 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids/" + i16,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/cell_ids/items/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err291];
}
else {
vErrors.push(err291);
}
errors++;
}
}
let i17 = data98.length;
let j3;
if(i17 > 1){
const indices3 = {};
for(;i17--;){
let item3 = data98[i17];
if(typeof item3 !== "string"){
continue;
}
if(typeof indices3[item3] == "number"){
j3 = indices3[item3];
const err292 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/cell_ids/uniqueItems",keyword:"uniqueItems",params:{i: i17, j: j3},message:"must NOT have duplicate items (items ## "+j3+" and "+i17+" are identical)"};
if(vErrors === null){
vErrors = [err292];
}
else {
vErrors.push(err292);
}
errors++;
break;
}
indices3[item3] = i17;
}
}
}
else {
const err293 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/cell_ids",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/properties/cell_ids/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err293];
}
else {
vErrors.push(err293);
}
errors++;
}
}
}
else {
const err294 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/4/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err294];
}
else {
vErrors.push(err294);
}
errors++;
}
var _valid0 = _errs184 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 4];
}
else {
if(_valid0){
valid12 = true;
passing0 = 4;
if(props0 !== true){
props0 = true;
}
}
const _errs213 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err295 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err295];
}
else {
vErrors.push(err295);
}
errors++;
}
if(data23.element_id === undefined){
const err296 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err296];
}
else {
vErrors.push(err296);
}
errors++;
}
if(data23.from_element_id === undefined){
const err297 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/required",keyword:"required",params:{missingProperty: "from_element_id"},message:"must have required property '"+"from_element_id"+"'"};
if(vErrors === null){
vErrors = [err297];
}
else {
vErrors.push(err297);
}
errors++;
}
if(data23.to_element_id === undefined){
const err298 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/required",keyword:"required",params:{missingProperty: "to_element_id"},message:"must have required property '"+"to_element_id"+"'"};
if(vErrors === null){
vErrors = [err298];
}
else {
vErrors.push(err298);
}
errors++;
}
for(const key18 in data23){
if(!((((((key18 === "type") || (key18 === "element_id")) || (key18 === "slot")) || (key18 === "from_element_id")) || (key18 === "to_element_id")) || (key18 === "timing"))){
const err299 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key18},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err299];
}
else {
vErrors.push(err299);
}
errors++;
}
}
if(data23.type !== undefined){
if("arrow" !== data23.type){
const err300 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/type/const",keyword:"const",params:{allowedValue: "arrow"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err300];
}
else {
vErrors.push(err300);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data101 = data23.element_id;
if(typeof data101 === "string"){
if(func2(data101) < 1){
const err301 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err301];
}
else {
vErrors.push(err301);
}
errors++;
}
}
else {
const err302 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err302];
}
else {
vErrors.push(err302);
}
errors++;
}
}
if(data23.slot !== undefined){
let data102 = data23.slot;
if(!(((((data102 === "main") || (data102 === "left")) || (data102 === "right")) || (data102 === "bottom")) || (data102 === "overlay"))){
const err303 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[5].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err303];
}
else {
vErrors.push(err303);
}
errors++;
}
}
if(data23.from_element_id !== undefined){
if(typeof data23.from_element_id !== "string"){
const err304 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/from_element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/from_element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err304];
}
else {
vErrors.push(err304);
}
errors++;
}
}
if(data23.to_element_id !== undefined){
if(typeof data23.to_element_id !== "string"){
const err305 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/to_element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/to_element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err305];
}
else {
vErrors.push(err305);
}
errors++;
}
}
if(data23.timing !== undefined){
let data105 = data23.timing;
if(data105 && typeof data105 == "object" && !Array.isArray(data105)){
if(data105.start === undefined){
const err306 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err306];
}
else {
vErrors.push(err306);
}
errors++;
}
if(data105.end === undefined){
const err307 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err307];
}
else {
vErrors.push(err307);
}
errors++;
}
for(const key19 in data105){
if(!((key19 === "start") || (key19 === "end"))){
const err308 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key19},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err308];
}
else {
vErrors.push(err308);
}
errors++;
}
}
if(data105.start !== undefined){
let data106 = data105.start;
if(typeof data106 == "number"){
if(data106 > 1 || isNaN(data106)){
const err309 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err309];
}
else {
vErrors.push(err309);
}
errors++;
}
if(data106 < 0 || isNaN(data106)){
const err310 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err310];
}
else {
vErrors.push(err310);
}
errors++;
}
}
else {
const err311 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err311];
}
else {
vErrors.push(err311);
}
errors++;
}
}
if(data105.end !== undefined){
let data107 = data105.end;
if(typeof data107 == "number"){
if(data107 > 1 || isNaN(data107)){
const err312 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err312];
}
else {
vErrors.push(err312);
}
errors++;
}
if(data107 < 0 || isNaN(data107)){
const err313 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err313];
}
else {
vErrors.push(err313);
}
errors++;
}
}
else {
const err314 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err314];
}
else {
vErrors.push(err314);
}
errors++;
}
}
}
else {
const err315 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err315];
}
else {
vErrors.push(err315);
}
errors++;
}
}
}
else {
const err316 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/5/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err316];
}
else {
vErrors.push(err316);
}
errors++;
}
var _valid0 = _errs213 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 5];
}
else {
if(_valid0){
valid12 = true;
passing0 = 5;
if(props0 !== true){
props0 = true;
}
}
const _errs231 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err317 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err317];
}
else {
vErrors.push(err317);
}
errors++;
}
if(data23.target === undefined){
const err318 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/required",keyword:"required",params:{missingProperty: "target"},message:"must have required property '"+"target"+"'"};
if(vErrors === null){
vErrors = [err318];
}
else {
vErrors.push(err318);
}
errors++;
}
for(const key20 in data23){
if(!(((((key20 === "type") || (key20 === "element_id")) || (key20 === "slot")) || (key20 === "target")) || (key20 === "timing"))){
const err319 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key20},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err319];
}
else {
vErrors.push(err319);
}
errors++;
}
}
if(data23.type !== undefined){
if("clear" !== data23.type){
const err320 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/type/const",keyword:"const",params:{allowedValue: "clear"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err320];
}
else {
vErrors.push(err320);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data109 = data23.element_id;
if(typeof data109 === "string"){
if(func2(data109) < 1){
const err321 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err321];
}
else {
vErrors.push(err321);
}
errors++;
}
}
else {
const err322 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err322];
}
else {
vErrors.push(err322);
}
errors++;
}
}
if(data23.slot !== undefined){
let data110 = data23.slot;
if(!(((((data110 === "main") || (data110 === "left")) || (data110 === "right")) || (data110 === "bottom")) || (data110 === "overlay"))){
const err323 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[6].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err323];
}
else {
vErrors.push(err323);
}
errors++;
}
}
if(data23.target !== undefined){
let data111 = data23.target;
if(typeof data111 === "string"){
if(func2(data111) < 1){
const err324 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/target",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/target/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err324];
}
else {
vErrors.push(err324);
}
errors++;
}
}
else {
const err325 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/target",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/target/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err325];
}
else {
vErrors.push(err325);
}
errors++;
}
}
if(data23.timing !== undefined){
let data112 = data23.timing;
if(data112 && typeof data112 == "object" && !Array.isArray(data112)){
if(data112.start === undefined){
const err326 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err326];
}
else {
vErrors.push(err326);
}
errors++;
}
if(data112.end === undefined){
const err327 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err327];
}
else {
vErrors.push(err327);
}
errors++;
}
for(const key21 in data112){
if(!((key21 === "start") || (key21 === "end"))){
const err328 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key21},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err328];
}
else {
vErrors.push(err328);
}
errors++;
}
}
if(data112.start !== undefined){
let data113 = data112.start;
if(typeof data113 == "number"){
if(data113 > 1 || isNaN(data113)){
const err329 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err329];
}
else {
vErrors.push(err329);
}
errors++;
}
if(data113 < 0 || isNaN(data113)){
const err330 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err330];
}
else {
vErrors.push(err330);
}
errors++;
}
}
else {
const err331 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err331];
}
else {
vErrors.push(err331);
}
errors++;
}
}
if(data112.end !== undefined){
let data114 = data112.end;
if(typeof data114 == "number"){
if(data114 > 1 || isNaN(data114)){
const err332 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err332];
}
else {
vErrors.push(err332);
}
errors++;
}
if(data114 < 0 || isNaN(data114)){
const err333 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err333];
}
else {
vErrors.push(err333);
}
errors++;
}
}
else {
const err334 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err334];
}
else {
vErrors.push(err334);
}
errors++;
}
}
}
else {
const err335 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err335];
}
else {
vErrors.push(err335);
}
errors++;
}
}
}
else {
const err336 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/6/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err336];
}
else {
vErrors.push(err336);
}
errors++;
}
var _valid0 = _errs231 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 6];
}
else {
if(_valid0){
valid12 = true;
passing0 = 6;
if(props0 !== true){
props0 = true;
}
}
const _errs247 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err337 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err337];
}
else {
vErrors.push(err337);
}
errors++;
}
if(data23.element_id === undefined){
const err338 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err338];
}
else {
vErrors.push(err338);
}
errors++;
}
if(data23.geometry === undefined){
const err339 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/required",keyword:"required",params:{missingProperty: "geometry"},message:"must have required property '"+"geometry"+"'"};
if(vErrors === null){
vErrors = [err339];
}
else {
vErrors.push(err339);
}
errors++;
}
for(const key22 in data23){
if(!(((((((key22 === "type") || (key22 === "element_id")) || (key22 === "slot")) || (key22 === "geometry")) || (key22 === "stroke")) || (key22 === "stroke_width")) || (key22 === "timing"))){
const err340 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key22},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err340];
}
else {
vErrors.push(err340);
}
errors++;
}
}
if(data23.type !== undefined){
if("line" !== data23.type){
const err341 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/type/const",keyword:"const",params:{allowedValue: "line"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err341];
}
else {
vErrors.push(err341);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data116 = data23.element_id;
if(typeof data116 === "string"){
if(func2(data116) > 200){
const err342 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/element_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err342];
}
else {
vErrors.push(err342);
}
errors++;
}
if(func2(data116) < 1){
const err343 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err343];
}
else {
vErrors.push(err343);
}
errors++;
}
}
else {
const err344 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err344];
}
else {
vErrors.push(err344);
}
errors++;
}
}
if(data23.slot !== undefined){
let data117 = data23.slot;
if(!(((((data117 === "main") || (data117 === "left")) || (data117 === "right")) || (data117 === "bottom")) || (data117 === "overlay"))){
const err345 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[7].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err345];
}
else {
vErrors.push(err345);
}
errors++;
}
}
if(data23.geometry !== undefined){
let data118 = data23.geometry;
if(data118 && typeof data118 == "object" && !Array.isArray(data118)){
if(data118.x1 === undefined){
const err346 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/required",keyword:"required",params:{missingProperty: "x1"},message:"must have required property '"+"x1"+"'"};
if(vErrors === null){
vErrors = [err346];
}
else {
vErrors.push(err346);
}
errors++;
}
if(data118.y1 === undefined){
const err347 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/required",keyword:"required",params:{missingProperty: "y1"},message:"must have required property '"+"y1"+"'"};
if(vErrors === null){
vErrors = [err347];
}
else {
vErrors.push(err347);
}
errors++;
}
if(data118.x2 === undefined){
const err348 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/required",keyword:"required",params:{missingProperty: "x2"},message:"must have required property '"+"x2"+"'"};
if(vErrors === null){
vErrors = [err348];
}
else {
vErrors.push(err348);
}
errors++;
}
if(data118.y2 === undefined){
const err349 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/required",keyword:"required",params:{missingProperty: "y2"},message:"must have required property '"+"y2"+"'"};
if(vErrors === null){
vErrors = [err349];
}
else {
vErrors.push(err349);
}
errors++;
}
for(const key23 in data118){
if(!((((key23 === "x1") || (key23 === "y1")) || (key23 === "x2")) || (key23 === "y2"))){
const err350 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key23},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err350];
}
else {
vErrors.push(err350);
}
errors++;
}
}
if(data118.x1 !== undefined){
let data119 = data118.x1;
if(typeof data119 == "number"){
if(data119 > 1 || isNaN(data119)){
const err351 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/x1/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err351];
}
else {
vErrors.push(err351);
}
errors++;
}
if(data119 < 0 || isNaN(data119)){
const err352 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/x1/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err352];
}
else {
vErrors.push(err352);
}
errors++;
}
}
else {
const err353 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/x1/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err353];
}
else {
vErrors.push(err353);
}
errors++;
}
}
if(data118.y1 !== undefined){
let data120 = data118.y1;
if(typeof data120 == "number"){
if(data120 > 1 || isNaN(data120)){
const err354 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/y1/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err354];
}
else {
vErrors.push(err354);
}
errors++;
}
if(data120 < 0 || isNaN(data120)){
const err355 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/y1/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err355];
}
else {
vErrors.push(err355);
}
errors++;
}
}
else {
const err356 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/y1/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err356];
}
else {
vErrors.push(err356);
}
errors++;
}
}
if(data118.x2 !== undefined){
let data121 = data118.x2;
if(typeof data121 == "number"){
if(data121 > 1 || isNaN(data121)){
const err357 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/x2/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err357];
}
else {
vErrors.push(err357);
}
errors++;
}
if(data121 < 0 || isNaN(data121)){
const err358 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/x2/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err358];
}
else {
vErrors.push(err358);
}
errors++;
}
}
else {
const err359 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/x2/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err359];
}
else {
vErrors.push(err359);
}
errors++;
}
}
if(data118.y2 !== undefined){
let data122 = data118.y2;
if(typeof data122 == "number"){
if(data122 > 1 || isNaN(data122)){
const err360 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/y2/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err360];
}
else {
vErrors.push(err360);
}
errors++;
}
if(data122 < 0 || isNaN(data122)){
const err361 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/y2/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err361];
}
else {
vErrors.push(err361);
}
errors++;
}
}
else {
const err362 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/properties/y2/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err362];
}
else {
vErrors.push(err362);
}
errors++;
}
}
}
else {
const err363 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/geometry/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err363];
}
else {
vErrors.push(err363);
}
errors++;
}
}
if(data23.stroke !== undefined){
let data123 = data23.stroke;
if(!(((data123 === "chalk") || (data123 === "accent")) || (data123 === "warning"))){
const err364 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/stroke/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[7].properties.stroke.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err364];
}
else {
vErrors.push(err364);
}
errors++;
}
}
if(data23.stroke_width !== undefined){
let data124 = data23.stroke_width;
if(typeof data124 == "number"){
if(data124 > 6 || isNaN(data124)){
const err365 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/stroke_width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 6},message:"must be <= 6"};
if(vErrors === null){
vErrors = [err365];
}
else {
vErrors.push(err365);
}
errors++;
}
if(data124 < 1 || isNaN(data124)){
const err366 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/stroke_width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err366];
}
else {
vErrors.push(err366);
}
errors++;
}
}
else {
const err367 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/stroke_width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err367];
}
else {
vErrors.push(err367);
}
errors++;
}
}
if(data23.timing !== undefined){
let data125 = data23.timing;
if(data125 && typeof data125 == "object" && !Array.isArray(data125)){
if(data125.start === undefined){
const err368 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err368];
}
else {
vErrors.push(err368);
}
errors++;
}
if(data125.end === undefined){
const err369 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err369];
}
else {
vErrors.push(err369);
}
errors++;
}
for(const key24 in data125){
if(!((key24 === "start") || (key24 === "end"))){
const err370 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key24},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err370];
}
else {
vErrors.push(err370);
}
errors++;
}
}
if(data125.start !== undefined){
let data126 = data125.start;
if(typeof data126 == "number"){
if(data126 > 1 || isNaN(data126)){
const err371 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err371];
}
else {
vErrors.push(err371);
}
errors++;
}
if(data126 < 0 || isNaN(data126)){
const err372 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err372];
}
else {
vErrors.push(err372);
}
errors++;
}
}
else {
const err373 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err373];
}
else {
vErrors.push(err373);
}
errors++;
}
}
if(data125.end !== undefined){
let data127 = data125.end;
if(typeof data127 == "number"){
if(data127 > 1 || isNaN(data127)){
const err374 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err374];
}
else {
vErrors.push(err374);
}
errors++;
}
if(data127 < 0 || isNaN(data127)){
const err375 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err375];
}
else {
vErrors.push(err375);
}
errors++;
}
}
else {
const err376 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err376];
}
else {
vErrors.push(err376);
}
errors++;
}
}
}
else {
const err377 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err377];
}
else {
vErrors.push(err377);
}
errors++;
}
}
}
else {
const err378 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/7/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err378];
}
else {
vErrors.push(err378);
}
errors++;
}
var _valid0 = _errs247 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 7];
}
else {
if(_valid0){
valid12 = true;
passing0 = 7;
if(props0 !== true){
props0 = true;
}
}
const _errs275 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err379 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err379];
}
else {
vErrors.push(err379);
}
errors++;
}
if(data23.element_id === undefined){
const err380 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err380];
}
else {
vErrors.push(err380);
}
errors++;
}
if(data23.geometry === undefined){
const err381 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/required",keyword:"required",params:{missingProperty: "geometry"},message:"must have required property '"+"geometry"+"'"};
if(vErrors === null){
vErrors = [err381];
}
else {
vErrors.push(err381);
}
errors++;
}
for(const key25 in data23){
if(!(((((((key25 === "type") || (key25 === "element_id")) || (key25 === "slot")) || (key25 === "geometry")) || (key25 === "stroke")) || (key25 === "stroke_width")) || (key25 === "timing"))){
const err382 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key25},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err382];
}
else {
vErrors.push(err382);
}
errors++;
}
}
if(data23.type !== undefined){
if("arrow" !== data23.type){
const err383 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/type/const",keyword:"const",params:{allowedValue: "arrow"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err383];
}
else {
vErrors.push(err383);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data129 = data23.element_id;
if(typeof data129 === "string"){
if(func2(data129) > 200){
const err384 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/element_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err384];
}
else {
vErrors.push(err384);
}
errors++;
}
if(func2(data129) < 1){
const err385 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err385];
}
else {
vErrors.push(err385);
}
errors++;
}
}
else {
const err386 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err386];
}
else {
vErrors.push(err386);
}
errors++;
}
}
if(data23.slot !== undefined){
let data130 = data23.slot;
if(!(((((data130 === "main") || (data130 === "left")) || (data130 === "right")) || (data130 === "bottom")) || (data130 === "overlay"))){
const err387 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[8].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err387];
}
else {
vErrors.push(err387);
}
errors++;
}
}
if(data23.geometry !== undefined){
let data131 = data23.geometry;
if(data131 && typeof data131 == "object" && !Array.isArray(data131)){
if(data131.x1 === undefined){
const err388 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/required",keyword:"required",params:{missingProperty: "x1"},message:"must have required property '"+"x1"+"'"};
if(vErrors === null){
vErrors = [err388];
}
else {
vErrors.push(err388);
}
errors++;
}
if(data131.y1 === undefined){
const err389 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/required",keyword:"required",params:{missingProperty: "y1"},message:"must have required property '"+"y1"+"'"};
if(vErrors === null){
vErrors = [err389];
}
else {
vErrors.push(err389);
}
errors++;
}
if(data131.x2 === undefined){
const err390 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/required",keyword:"required",params:{missingProperty: "x2"},message:"must have required property '"+"x2"+"'"};
if(vErrors === null){
vErrors = [err390];
}
else {
vErrors.push(err390);
}
errors++;
}
if(data131.y2 === undefined){
const err391 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/required",keyword:"required",params:{missingProperty: "y2"},message:"must have required property '"+"y2"+"'"};
if(vErrors === null){
vErrors = [err391];
}
else {
vErrors.push(err391);
}
errors++;
}
for(const key26 in data131){
if(!((((key26 === "x1") || (key26 === "y1")) || (key26 === "x2")) || (key26 === "y2"))){
const err392 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key26},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err392];
}
else {
vErrors.push(err392);
}
errors++;
}
}
if(data131.x1 !== undefined){
let data132 = data131.x1;
if(typeof data132 == "number"){
if(data132 > 1 || isNaN(data132)){
const err393 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/x1/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err393];
}
else {
vErrors.push(err393);
}
errors++;
}
if(data132 < 0 || isNaN(data132)){
const err394 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/x1/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err394];
}
else {
vErrors.push(err394);
}
errors++;
}
}
else {
const err395 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/x1/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err395];
}
else {
vErrors.push(err395);
}
errors++;
}
}
if(data131.y1 !== undefined){
let data133 = data131.y1;
if(typeof data133 == "number"){
if(data133 > 1 || isNaN(data133)){
const err396 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/y1/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err396];
}
else {
vErrors.push(err396);
}
errors++;
}
if(data133 < 0 || isNaN(data133)){
const err397 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/y1/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err397];
}
else {
vErrors.push(err397);
}
errors++;
}
}
else {
const err398 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y1",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/y1/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err398];
}
else {
vErrors.push(err398);
}
errors++;
}
}
if(data131.x2 !== undefined){
let data134 = data131.x2;
if(typeof data134 == "number"){
if(data134 > 1 || isNaN(data134)){
const err399 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/x2/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err399];
}
else {
vErrors.push(err399);
}
errors++;
}
if(data134 < 0 || isNaN(data134)){
const err400 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/x2/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err400];
}
else {
vErrors.push(err400);
}
errors++;
}
}
else {
const err401 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/x2/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err401];
}
else {
vErrors.push(err401);
}
errors++;
}
}
if(data131.y2 !== undefined){
let data135 = data131.y2;
if(typeof data135 == "number"){
if(data135 > 1 || isNaN(data135)){
const err402 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/y2/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err402];
}
else {
vErrors.push(err402);
}
errors++;
}
if(data135 < 0 || isNaN(data135)){
const err403 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/y2/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err403];
}
else {
vErrors.push(err403);
}
errors++;
}
}
else {
const err404 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y2",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/properties/y2/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err404];
}
else {
vErrors.push(err404);
}
errors++;
}
}
}
else {
const err405 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/geometry/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err405];
}
else {
vErrors.push(err405);
}
errors++;
}
}
if(data23.stroke !== undefined){
let data136 = data23.stroke;
if(!(((data136 === "chalk") || (data136 === "accent")) || (data136 === "warning"))){
const err406 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/stroke/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[8].properties.stroke.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err406];
}
else {
vErrors.push(err406);
}
errors++;
}
}
if(data23.stroke_width !== undefined){
let data137 = data23.stroke_width;
if(typeof data137 == "number"){
if(data137 > 6 || isNaN(data137)){
const err407 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/stroke_width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 6},message:"must be <= 6"};
if(vErrors === null){
vErrors = [err407];
}
else {
vErrors.push(err407);
}
errors++;
}
if(data137 < 1 || isNaN(data137)){
const err408 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/stroke_width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err408];
}
else {
vErrors.push(err408);
}
errors++;
}
}
else {
const err409 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/stroke_width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err409];
}
else {
vErrors.push(err409);
}
errors++;
}
}
if(data23.timing !== undefined){
let data138 = data23.timing;
if(data138 && typeof data138 == "object" && !Array.isArray(data138)){
if(data138.start === undefined){
const err410 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err410];
}
else {
vErrors.push(err410);
}
errors++;
}
if(data138.end === undefined){
const err411 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err411];
}
else {
vErrors.push(err411);
}
errors++;
}
for(const key27 in data138){
if(!((key27 === "start") || (key27 === "end"))){
const err412 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key27},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err412];
}
else {
vErrors.push(err412);
}
errors++;
}
}
if(data138.start !== undefined){
let data139 = data138.start;
if(typeof data139 == "number"){
if(data139 > 1 || isNaN(data139)){
const err413 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err413];
}
else {
vErrors.push(err413);
}
errors++;
}
if(data139 < 0 || isNaN(data139)){
const err414 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err414];
}
else {
vErrors.push(err414);
}
errors++;
}
}
else {
const err415 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err415];
}
else {
vErrors.push(err415);
}
errors++;
}
}
if(data138.end !== undefined){
let data140 = data138.end;
if(typeof data140 == "number"){
if(data140 > 1 || isNaN(data140)){
const err416 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err416];
}
else {
vErrors.push(err416);
}
errors++;
}
if(data140 < 0 || isNaN(data140)){
const err417 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err417];
}
else {
vErrors.push(err417);
}
errors++;
}
}
else {
const err418 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err418];
}
else {
vErrors.push(err418);
}
errors++;
}
}
}
else {
const err419 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err419];
}
else {
vErrors.push(err419);
}
errors++;
}
}
}
else {
const err420 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/8/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err420];
}
else {
vErrors.push(err420);
}
errors++;
}
var _valid0 = _errs275 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 8];
}
else {
if(_valid0){
valid12 = true;
passing0 = 8;
if(props0 !== true){
props0 = true;
}
}
const _errs303 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err421 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err421];
}
else {
vErrors.push(err421);
}
errors++;
}
if(data23.element_id === undefined){
const err422 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err422];
}
else {
vErrors.push(err422);
}
errors++;
}
if(data23.geometry === undefined){
const err423 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/required",keyword:"required",params:{missingProperty: "geometry"},message:"must have required property '"+"geometry"+"'"};
if(vErrors === null){
vErrors = [err423];
}
else {
vErrors.push(err423);
}
errors++;
}
for(const key28 in data23){
if(!(((((((key28 === "type") || (key28 === "element_id")) || (key28 === "slot")) || (key28 === "geometry")) || (key28 === "stroke")) || (key28 === "stroke_width")) || (key28 === "timing"))){
const err424 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key28},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err424];
}
else {
vErrors.push(err424);
}
errors++;
}
}
if(data23.type !== undefined){
if("rect" !== data23.type){
const err425 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/type/const",keyword:"const",params:{allowedValue: "rect"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err425];
}
else {
vErrors.push(err425);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data142 = data23.element_id;
if(typeof data142 === "string"){
if(func2(data142) > 200){
const err426 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/element_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err426];
}
else {
vErrors.push(err426);
}
errors++;
}
if(func2(data142) < 1){
const err427 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err427];
}
else {
vErrors.push(err427);
}
errors++;
}
}
else {
const err428 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err428];
}
else {
vErrors.push(err428);
}
errors++;
}
}
if(data23.slot !== undefined){
let data143 = data23.slot;
if(!(((((data143 === "main") || (data143 === "left")) || (data143 === "right")) || (data143 === "bottom")) || (data143 === "overlay"))){
const err429 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[9].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err429];
}
else {
vErrors.push(err429);
}
errors++;
}
}
if(data23.geometry !== undefined){
let data144 = data23.geometry;
if(data144 && typeof data144 == "object" && !Array.isArray(data144)){
if(data144.x === undefined){
const err430 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err430];
}
else {
vErrors.push(err430);
}
errors++;
}
if(data144.y === undefined){
const err431 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err431];
}
else {
vErrors.push(err431);
}
errors++;
}
if(data144.width === undefined){
const err432 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err432];
}
else {
vErrors.push(err432);
}
errors++;
}
if(data144.height === undefined){
const err433 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err433];
}
else {
vErrors.push(err433);
}
errors++;
}
for(const key29 in data144){
if(!((((key29 === "x") || (key29 === "y")) || (key29 === "width")) || (key29 === "height"))){
const err434 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key29},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err434];
}
else {
vErrors.push(err434);
}
errors++;
}
}
if(data144.x !== undefined){
let data145 = data144.x;
if(typeof data145 == "number"){
if(data145 > 1 || isNaN(data145)){
const err435 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/x/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err435];
}
else {
vErrors.push(err435);
}
errors++;
}
if(data145 < 0 || isNaN(data145)){
const err436 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/x/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err436];
}
else {
vErrors.push(err436);
}
errors++;
}
}
else {
const err437 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err437];
}
else {
vErrors.push(err437);
}
errors++;
}
}
if(data144.y !== undefined){
let data146 = data144.y;
if(typeof data146 == "number"){
if(data146 > 1 || isNaN(data146)){
const err438 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/y/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err438];
}
else {
vErrors.push(err438);
}
errors++;
}
if(data146 < 0 || isNaN(data146)){
const err439 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/y/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err439];
}
else {
vErrors.push(err439);
}
errors++;
}
}
else {
const err440 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err440];
}
else {
vErrors.push(err440);
}
errors++;
}
}
if(data144.width !== undefined){
let data147 = data144.width;
if(typeof data147 == "number"){
if(data147 > 1 || isNaN(data147)){
const err441 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err441];
}
else {
vErrors.push(err441);
}
errors++;
}
if(data147 < 0 || isNaN(data147)){
const err442 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err442];
}
else {
vErrors.push(err442);
}
errors++;
}
if(data147 <= 0 || isNaN(data147)){
const err443 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err443];
}
else {
vErrors.push(err443);
}
errors++;
}
}
else {
const err444 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err444];
}
else {
vErrors.push(err444);
}
errors++;
}
}
if(data144.height !== undefined){
let data148 = data144.height;
if(typeof data148 == "number"){
if(data148 > 1 || isNaN(data148)){
const err445 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/height/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err445];
}
else {
vErrors.push(err445);
}
errors++;
}
if(data148 < 0 || isNaN(data148)){
const err446 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/height/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err446];
}
else {
vErrors.push(err446);
}
errors++;
}
if(data148 <= 0 || isNaN(data148)){
const err447 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err447];
}
else {
vErrors.push(err447);
}
errors++;
}
}
else {
const err448 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err448];
}
else {
vErrors.push(err448);
}
errors++;
}
}
}
else {
const err449 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/geometry/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err449];
}
else {
vErrors.push(err449);
}
errors++;
}
}
if(data23.stroke !== undefined){
let data149 = data23.stroke;
if(!(((data149 === "chalk") || (data149 === "accent")) || (data149 === "warning"))){
const err450 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/stroke/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[9].properties.stroke.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err450];
}
else {
vErrors.push(err450);
}
errors++;
}
}
if(data23.stroke_width !== undefined){
let data150 = data23.stroke_width;
if(typeof data150 == "number"){
if(data150 > 6 || isNaN(data150)){
const err451 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/stroke_width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 6},message:"must be <= 6"};
if(vErrors === null){
vErrors = [err451];
}
else {
vErrors.push(err451);
}
errors++;
}
if(data150 < 1 || isNaN(data150)){
const err452 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/stroke_width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err452];
}
else {
vErrors.push(err452);
}
errors++;
}
}
else {
const err453 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/stroke_width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err453];
}
else {
vErrors.push(err453);
}
errors++;
}
}
if(data23.timing !== undefined){
let data151 = data23.timing;
if(data151 && typeof data151 == "object" && !Array.isArray(data151)){
if(data151.start === undefined){
const err454 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err454];
}
else {
vErrors.push(err454);
}
errors++;
}
if(data151.end === undefined){
const err455 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err455];
}
else {
vErrors.push(err455);
}
errors++;
}
for(const key30 in data151){
if(!((key30 === "start") || (key30 === "end"))){
const err456 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key30},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err456];
}
else {
vErrors.push(err456);
}
errors++;
}
}
if(data151.start !== undefined){
let data152 = data151.start;
if(typeof data152 == "number"){
if(data152 > 1 || isNaN(data152)){
const err457 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err457];
}
else {
vErrors.push(err457);
}
errors++;
}
if(data152 < 0 || isNaN(data152)){
const err458 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err458];
}
else {
vErrors.push(err458);
}
errors++;
}
}
else {
const err459 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err459];
}
else {
vErrors.push(err459);
}
errors++;
}
}
if(data151.end !== undefined){
let data153 = data151.end;
if(typeof data153 == "number"){
if(data153 > 1 || isNaN(data153)){
const err460 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err460];
}
else {
vErrors.push(err460);
}
errors++;
}
if(data153 < 0 || isNaN(data153)){
const err461 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err461];
}
else {
vErrors.push(err461);
}
errors++;
}
}
else {
const err462 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err462];
}
else {
vErrors.push(err462);
}
errors++;
}
}
}
else {
const err463 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err463];
}
else {
vErrors.push(err463);
}
errors++;
}
}
}
else {
const err464 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/9/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err464];
}
else {
vErrors.push(err464);
}
errors++;
}
var _valid0 = _errs303 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 9];
}
else {
if(_valid0){
valid12 = true;
passing0 = 9;
if(props0 !== true){
props0 = true;
}
}
const _errs331 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err465 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err465];
}
else {
vErrors.push(err465);
}
errors++;
}
if(data23.element_id === undefined){
const err466 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err466];
}
else {
vErrors.push(err466);
}
errors++;
}
if(data23.geometry === undefined){
const err467 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/required",keyword:"required",params:{missingProperty: "geometry"},message:"must have required property '"+"geometry"+"'"};
if(vErrors === null){
vErrors = [err467];
}
else {
vErrors.push(err467);
}
errors++;
}
for(const key31 in data23){
if(!(((((((key31 === "type") || (key31 === "element_id")) || (key31 === "slot")) || (key31 === "geometry")) || (key31 === "stroke")) || (key31 === "stroke_width")) || (key31 === "timing"))){
const err468 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key31},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err468];
}
else {
vErrors.push(err468);
}
errors++;
}
}
if(data23.type !== undefined){
if("ellipse" !== data23.type){
const err469 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/type/const",keyword:"const",params:{allowedValue: "ellipse"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err469];
}
else {
vErrors.push(err469);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data155 = data23.element_id;
if(typeof data155 === "string"){
if(func2(data155) > 200){
const err470 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/element_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err470];
}
else {
vErrors.push(err470);
}
errors++;
}
if(func2(data155) < 1){
const err471 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err471];
}
else {
vErrors.push(err471);
}
errors++;
}
}
else {
const err472 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err472];
}
else {
vErrors.push(err472);
}
errors++;
}
}
if(data23.slot !== undefined){
let data156 = data23.slot;
if(!(((((data156 === "main") || (data156 === "left")) || (data156 === "right")) || (data156 === "bottom")) || (data156 === "overlay"))){
const err473 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[10].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err473];
}
else {
vErrors.push(err473);
}
errors++;
}
}
if(data23.geometry !== undefined){
let data157 = data23.geometry;
if(data157 && typeof data157 == "object" && !Array.isArray(data157)){
if(data157.x === undefined){
const err474 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err474];
}
else {
vErrors.push(err474);
}
errors++;
}
if(data157.y === undefined){
const err475 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err475];
}
else {
vErrors.push(err475);
}
errors++;
}
if(data157.width === undefined){
const err476 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err476];
}
else {
vErrors.push(err476);
}
errors++;
}
if(data157.height === undefined){
const err477 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err477];
}
else {
vErrors.push(err477);
}
errors++;
}
for(const key32 in data157){
if(!((((key32 === "x") || (key32 === "y")) || (key32 === "width")) || (key32 === "height"))){
const err478 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key32},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err478];
}
else {
vErrors.push(err478);
}
errors++;
}
}
if(data157.x !== undefined){
let data158 = data157.x;
if(typeof data158 == "number"){
if(data158 > 1 || isNaN(data158)){
const err479 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/x/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err479];
}
else {
vErrors.push(err479);
}
errors++;
}
if(data158 < 0 || isNaN(data158)){
const err480 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/x/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err480];
}
else {
vErrors.push(err480);
}
errors++;
}
}
else {
const err481 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err481];
}
else {
vErrors.push(err481);
}
errors++;
}
}
if(data157.y !== undefined){
let data159 = data157.y;
if(typeof data159 == "number"){
if(data159 > 1 || isNaN(data159)){
const err482 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/y/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err482];
}
else {
vErrors.push(err482);
}
errors++;
}
if(data159 < 0 || isNaN(data159)){
const err483 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/y/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err483];
}
else {
vErrors.push(err483);
}
errors++;
}
}
else {
const err484 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err484];
}
else {
vErrors.push(err484);
}
errors++;
}
}
if(data157.width !== undefined){
let data160 = data157.width;
if(typeof data160 == "number"){
if(data160 > 1 || isNaN(data160)){
const err485 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err485];
}
else {
vErrors.push(err485);
}
errors++;
}
if(data160 < 0 || isNaN(data160)){
const err486 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err486];
}
else {
vErrors.push(err486);
}
errors++;
}
if(data160 <= 0 || isNaN(data160)){
const err487 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err487];
}
else {
vErrors.push(err487);
}
errors++;
}
}
else {
const err488 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err488];
}
else {
vErrors.push(err488);
}
errors++;
}
}
if(data157.height !== undefined){
let data161 = data157.height;
if(typeof data161 == "number"){
if(data161 > 1 || isNaN(data161)){
const err489 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/height/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err489];
}
else {
vErrors.push(err489);
}
errors++;
}
if(data161 < 0 || isNaN(data161)){
const err490 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/height/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err490];
}
else {
vErrors.push(err490);
}
errors++;
}
if(data161 <= 0 || isNaN(data161)){
const err491 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err491];
}
else {
vErrors.push(err491);
}
errors++;
}
}
else {
const err492 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err492];
}
else {
vErrors.push(err492);
}
errors++;
}
}
}
else {
const err493 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/geometry/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err493];
}
else {
vErrors.push(err493);
}
errors++;
}
}
if(data23.stroke !== undefined){
let data162 = data23.stroke;
if(!(((data162 === "chalk") || (data162 === "accent")) || (data162 === "warning"))){
const err494 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/stroke/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[10].properties.stroke.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err494];
}
else {
vErrors.push(err494);
}
errors++;
}
}
if(data23.stroke_width !== undefined){
let data163 = data23.stroke_width;
if(typeof data163 == "number"){
if(data163 > 6 || isNaN(data163)){
const err495 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/stroke_width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 6},message:"must be <= 6"};
if(vErrors === null){
vErrors = [err495];
}
else {
vErrors.push(err495);
}
errors++;
}
if(data163 < 1 || isNaN(data163)){
const err496 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/stroke_width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err496];
}
else {
vErrors.push(err496);
}
errors++;
}
}
else {
const err497 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/stroke_width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err497];
}
else {
vErrors.push(err497);
}
errors++;
}
}
if(data23.timing !== undefined){
let data164 = data23.timing;
if(data164 && typeof data164 == "object" && !Array.isArray(data164)){
if(data164.start === undefined){
const err498 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err498];
}
else {
vErrors.push(err498);
}
errors++;
}
if(data164.end === undefined){
const err499 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err499];
}
else {
vErrors.push(err499);
}
errors++;
}
for(const key33 in data164){
if(!((key33 === "start") || (key33 === "end"))){
const err500 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key33},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err500];
}
else {
vErrors.push(err500);
}
errors++;
}
}
if(data164.start !== undefined){
let data165 = data164.start;
if(typeof data165 == "number"){
if(data165 > 1 || isNaN(data165)){
const err501 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err501];
}
else {
vErrors.push(err501);
}
errors++;
}
if(data165 < 0 || isNaN(data165)){
const err502 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err502];
}
else {
vErrors.push(err502);
}
errors++;
}
}
else {
const err503 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err503];
}
else {
vErrors.push(err503);
}
errors++;
}
}
if(data164.end !== undefined){
let data166 = data164.end;
if(typeof data166 == "number"){
if(data166 > 1 || isNaN(data166)){
const err504 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err504];
}
else {
vErrors.push(err504);
}
errors++;
}
if(data166 < 0 || isNaN(data166)){
const err505 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err505];
}
else {
vErrors.push(err505);
}
errors++;
}
}
else {
const err506 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err506];
}
else {
vErrors.push(err506);
}
errors++;
}
}
}
else {
const err507 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err507];
}
else {
vErrors.push(err507);
}
errors++;
}
}
}
else {
const err508 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/10/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err508];
}
else {
vErrors.push(err508);
}
errors++;
}
var _valid0 = _errs331 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 10];
}
else {
if(_valid0){
valid12 = true;
passing0 = 10;
if(props0 !== true){
props0 = true;
}
}
const _errs359 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err509 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err509];
}
else {
vErrors.push(err509);
}
errors++;
}
if(data23.element_id === undefined){
const err510 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err510];
}
else {
vErrors.push(err510);
}
errors++;
}
if(data23.geometry === undefined){
const err511 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/required",keyword:"required",params:{missingProperty: "geometry"},message:"must have required property '"+"geometry"+"'"};
if(vErrors === null){
vErrors = [err511];
}
else {
vErrors.push(err511);
}
errors++;
}
for(const key34 in data23){
if(!(((((((key34 === "type") || (key34 === "element_id")) || (key34 === "slot")) || (key34 === "geometry")) || (key34 === "stroke")) || (key34 === "stroke_width")) || (key34 === "timing"))){
const err512 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key34},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err512];
}
else {
vErrors.push(err512);
}
errors++;
}
}
if(data23.type !== undefined){
if("circle" !== data23.type){
const err513 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/type/const",keyword:"const",params:{allowedValue: "circle"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err513];
}
else {
vErrors.push(err513);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data168 = data23.element_id;
if(typeof data168 === "string"){
if(func2(data168) > 200){
const err514 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/element_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err514];
}
else {
vErrors.push(err514);
}
errors++;
}
if(func2(data168) < 1){
const err515 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err515];
}
else {
vErrors.push(err515);
}
errors++;
}
}
else {
const err516 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err516];
}
else {
vErrors.push(err516);
}
errors++;
}
}
if(data23.slot !== undefined){
let data169 = data23.slot;
if(!(((((data169 === "main") || (data169 === "left")) || (data169 === "right")) || (data169 === "bottom")) || (data169 === "overlay"))){
const err517 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[11].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err517];
}
else {
vErrors.push(err517);
}
errors++;
}
}
if(data23.geometry !== undefined){
let data170 = data23.geometry;
if(data170 && typeof data170 == "object" && !Array.isArray(data170)){
if(data170.cx === undefined){
const err518 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/required",keyword:"required",params:{missingProperty: "cx"},message:"must have required property '"+"cx"+"'"};
if(vErrors === null){
vErrors = [err518];
}
else {
vErrors.push(err518);
}
errors++;
}
if(data170.cy === undefined){
const err519 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/required",keyword:"required",params:{missingProperty: "cy"},message:"must have required property '"+"cy"+"'"};
if(vErrors === null){
vErrors = [err519];
}
else {
vErrors.push(err519);
}
errors++;
}
if(data170.radius === undefined){
const err520 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/required",keyword:"required",params:{missingProperty: "radius"},message:"must have required property '"+"radius"+"'"};
if(vErrors === null){
vErrors = [err520];
}
else {
vErrors.push(err520);
}
errors++;
}
for(const key35 in data170){
if(!(((key35 === "cx") || (key35 === "cy")) || (key35 === "radius"))){
const err521 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key35},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err521];
}
else {
vErrors.push(err521);
}
errors++;
}
}
if(data170.cx !== undefined){
let data171 = data170.cx;
if(typeof data171 == "number"){
if(data171 > 1 || isNaN(data171)){
const err522 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/cx",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/cx/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err522];
}
else {
vErrors.push(err522);
}
errors++;
}
if(data171 < 0 || isNaN(data171)){
const err523 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/cx",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/cx/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err523];
}
else {
vErrors.push(err523);
}
errors++;
}
}
else {
const err524 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/cx",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/cx/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err524];
}
else {
vErrors.push(err524);
}
errors++;
}
}
if(data170.cy !== undefined){
let data172 = data170.cy;
if(typeof data172 == "number"){
if(data172 > 1 || isNaN(data172)){
const err525 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/cy",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/cy/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err525];
}
else {
vErrors.push(err525);
}
errors++;
}
if(data172 < 0 || isNaN(data172)){
const err526 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/cy",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/cy/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err526];
}
else {
vErrors.push(err526);
}
errors++;
}
}
else {
const err527 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/cy",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/cy/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err527];
}
else {
vErrors.push(err527);
}
errors++;
}
}
if(data170.radius !== undefined){
let data173 = data170.radius;
if(typeof data173 == "number"){
if(data173 > 0.5 || isNaN(data173)){
const err528 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/radius",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/radius/maximum",keyword:"maximum",params:{comparison: "<=", limit: 0.5},message:"must be <= 0.5"};
if(vErrors === null){
vErrors = [err528];
}
else {
vErrors.push(err528);
}
errors++;
}
if(data173 < 0 || isNaN(data173)){
const err529 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/radius",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/radius/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err529];
}
else {
vErrors.push(err529);
}
errors++;
}
if(data173 <= 0 || isNaN(data173)){
const err530 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/radius",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/radius/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err530];
}
else {
vErrors.push(err530);
}
errors++;
}
}
else {
const err531 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/radius",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/properties/radius/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err531];
}
else {
vErrors.push(err531);
}
errors++;
}
}
}
else {
const err532 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/geometry/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err532];
}
else {
vErrors.push(err532);
}
errors++;
}
}
if(data23.stroke !== undefined){
let data174 = data23.stroke;
if(!(((data174 === "chalk") || (data174 === "accent")) || (data174 === "warning"))){
const err533 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/stroke/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[11].properties.stroke.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err533];
}
else {
vErrors.push(err533);
}
errors++;
}
}
if(data23.stroke_width !== undefined){
let data175 = data23.stroke_width;
if(typeof data175 == "number"){
if(data175 > 6 || isNaN(data175)){
const err534 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/stroke_width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 6},message:"must be <= 6"};
if(vErrors === null){
vErrors = [err534];
}
else {
vErrors.push(err534);
}
errors++;
}
if(data175 < 1 || isNaN(data175)){
const err535 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/stroke_width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err535];
}
else {
vErrors.push(err535);
}
errors++;
}
}
else {
const err536 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/stroke_width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err536];
}
else {
vErrors.push(err536);
}
errors++;
}
}
if(data23.timing !== undefined){
let data176 = data23.timing;
if(data176 && typeof data176 == "object" && !Array.isArray(data176)){
if(data176.start === undefined){
const err537 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err537];
}
else {
vErrors.push(err537);
}
errors++;
}
if(data176.end === undefined){
const err538 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err538];
}
else {
vErrors.push(err538);
}
errors++;
}
for(const key36 in data176){
if(!((key36 === "start") || (key36 === "end"))){
const err539 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key36},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err539];
}
else {
vErrors.push(err539);
}
errors++;
}
}
if(data176.start !== undefined){
let data177 = data176.start;
if(typeof data177 == "number"){
if(data177 > 1 || isNaN(data177)){
const err540 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err540];
}
else {
vErrors.push(err540);
}
errors++;
}
if(data177 < 0 || isNaN(data177)){
const err541 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err541];
}
else {
vErrors.push(err541);
}
errors++;
}
}
else {
const err542 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err542];
}
else {
vErrors.push(err542);
}
errors++;
}
}
if(data176.end !== undefined){
let data178 = data176.end;
if(typeof data178 == "number"){
if(data178 > 1 || isNaN(data178)){
const err543 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err543];
}
else {
vErrors.push(err543);
}
errors++;
}
if(data178 < 0 || isNaN(data178)){
const err544 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err544];
}
else {
vErrors.push(err544);
}
errors++;
}
}
else {
const err545 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err545];
}
else {
vErrors.push(err545);
}
errors++;
}
}
}
else {
const err546 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err546];
}
else {
vErrors.push(err546);
}
errors++;
}
}
}
else {
const err547 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/11/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err547];
}
else {
vErrors.push(err547);
}
errors++;
}
var _valid0 = _errs359 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 11];
}
else {
if(_valid0){
valid12 = true;
passing0 = 11;
if(props0 !== true){
props0 = true;
}
}
const _errs385 = errors;
if(data23 && typeof data23 == "object" && !Array.isArray(data23)){
if(data23.type === undefined){
const err548 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/required",keyword:"required",params:{missingProperty: "type"},message:"must have required property '"+"type"+"'"};
if(vErrors === null){
vErrors = [err548];
}
else {
vErrors.push(err548);
}
errors++;
}
if(data23.element_id === undefined){
const err549 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/required",keyword:"required",params:{missingProperty: "element_id"},message:"must have required property '"+"element_id"+"'"};
if(vErrors === null){
vErrors = [err549];
}
else {
vErrors.push(err549);
}
errors++;
}
if(data23.geometry === undefined){
const err550 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/required",keyword:"required",params:{missingProperty: "geometry"},message:"must have required property '"+"geometry"+"'"};
if(vErrors === null){
vErrors = [err550];
}
else {
vErrors.push(err550);
}
errors++;
}
for(const key37 in data23){
if(!((((((((key37 === "type") || (key37 === "element_id")) || (key37 === "slot")) || (key37 === "geometry")) || (key37 === "stroke")) || (key37 === "stroke_width")) || (key37 === "timing")) || (key37 === "orientation"))){
const err551 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key37},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err551];
}
else {
vErrors.push(err551);
}
errors++;
}
}
if(data23.type !== undefined){
if("brace" !== data23.type){
const err552 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/type",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/type/const",keyword:"const",params:{allowedValue: "brace"},message:"must be equal to constant"};
if(vErrors === null){
vErrors = [err552];
}
else {
vErrors.push(err552);
}
errors++;
}
}
if(data23.element_id !== undefined){
let data180 = data23.element_id;
if(typeof data180 === "string"){
if(func2(data180) > 200){
const err553 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/element_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err553];
}
else {
vErrors.push(err553);
}
errors++;
}
if(func2(data180) < 1){
const err554 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/element_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err554];
}
else {
vErrors.push(err554);
}
errors++;
}
}
else {
const err555 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/element_id",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/element_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err555];
}
else {
vErrors.push(err555);
}
errors++;
}
}
if(data23.slot !== undefined){
let data181 = data23.slot;
if(!(((((data181 === "main") || (data181 === "left")) || (data181 === "right")) || (data181 === "bottom")) || (data181 === "overlay"))){
const err556 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/slot",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/slot/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[12].properties.slot.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err556];
}
else {
vErrors.push(err556);
}
errors++;
}
}
if(data23.geometry !== undefined){
let data182 = data23.geometry;
if(data182 && typeof data182 == "object" && !Array.isArray(data182)){
if(data182.x === undefined){
const err557 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/required",keyword:"required",params:{missingProperty: "x"},message:"must have required property '"+"x"+"'"};
if(vErrors === null){
vErrors = [err557];
}
else {
vErrors.push(err557);
}
errors++;
}
if(data182.y === undefined){
const err558 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/required",keyword:"required",params:{missingProperty: "y"},message:"must have required property '"+"y"+"'"};
if(vErrors === null){
vErrors = [err558];
}
else {
vErrors.push(err558);
}
errors++;
}
if(data182.width === undefined){
const err559 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/required",keyword:"required",params:{missingProperty: "width"},message:"must have required property '"+"width"+"'"};
if(vErrors === null){
vErrors = [err559];
}
else {
vErrors.push(err559);
}
errors++;
}
if(data182.height === undefined){
const err560 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/required",keyword:"required",params:{missingProperty: "height"},message:"must have required property '"+"height"+"'"};
if(vErrors === null){
vErrors = [err560];
}
else {
vErrors.push(err560);
}
errors++;
}
for(const key38 in data182){
if(!((((key38 === "x") || (key38 === "y")) || (key38 === "width")) || (key38 === "height"))){
const err561 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key38},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err561];
}
else {
vErrors.push(err561);
}
errors++;
}
}
if(data182.x !== undefined){
let data183 = data182.x;
if(typeof data183 == "number"){
if(data183 > 1 || isNaN(data183)){
const err562 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/x/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err562];
}
else {
vErrors.push(err562);
}
errors++;
}
if(data183 < 0 || isNaN(data183)){
const err563 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/x/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err563];
}
else {
vErrors.push(err563);
}
errors++;
}
}
else {
const err564 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/x",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/x/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err564];
}
else {
vErrors.push(err564);
}
errors++;
}
}
if(data182.y !== undefined){
let data184 = data182.y;
if(typeof data184 == "number"){
if(data184 > 1 || isNaN(data184)){
const err565 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/y/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err565];
}
else {
vErrors.push(err565);
}
errors++;
}
if(data184 < 0 || isNaN(data184)){
const err566 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/y/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err566];
}
else {
vErrors.push(err566);
}
errors++;
}
}
else {
const err567 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/y",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/y/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err567];
}
else {
vErrors.push(err567);
}
errors++;
}
}
if(data182.width !== undefined){
let data185 = data182.width;
if(typeof data185 == "number"){
if(data185 > 1 || isNaN(data185)){
const err568 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err568];
}
else {
vErrors.push(err568);
}
errors++;
}
if(data185 < 0 || isNaN(data185)){
const err569 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err569];
}
else {
vErrors.push(err569);
}
errors++;
}
if(data185 <= 0 || isNaN(data185)){
const err570 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/width/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err570];
}
else {
vErrors.push(err570);
}
errors++;
}
}
else {
const err571 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err571];
}
else {
vErrors.push(err571);
}
errors++;
}
}
if(data182.height !== undefined){
let data186 = data182.height;
if(typeof data186 == "number"){
if(data186 > 1 || isNaN(data186)){
const err572 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/height/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err572];
}
else {
vErrors.push(err572);
}
errors++;
}
if(data186 < 0 || isNaN(data186)){
const err573 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/height/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err573];
}
else {
vErrors.push(err573);
}
errors++;
}
if(data186 <= 0 || isNaN(data186)){
const err574 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/height/exclusiveMinimum",keyword:"exclusiveMinimum",params:{comparison: ">", limit: 0},message:"must be > 0"};
if(vErrors === null){
vErrors = [err574];
}
else {
vErrors.push(err574);
}
errors++;
}
}
else {
const err575 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry/height",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/properties/height/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err575];
}
else {
vErrors.push(err575);
}
errors++;
}
}
}
else {
const err576 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/geometry",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/geometry/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err576];
}
else {
vErrors.push(err576);
}
errors++;
}
}
if(data23.stroke !== undefined){
let data187 = data23.stroke;
if(!(((data187 === "chalk") || (data187 === "accent")) || (data187 === "warning"))){
const err577 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/stroke/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[12].properties.stroke.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err577];
}
else {
vErrors.push(err577);
}
errors++;
}
}
if(data23.stroke_width !== undefined){
let data188 = data23.stroke_width;
if(typeof data188 == "number"){
if(data188 > 6 || isNaN(data188)){
const err578 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/stroke_width/maximum",keyword:"maximum",params:{comparison: "<=", limit: 6},message:"must be <= 6"};
if(vErrors === null){
vErrors = [err578];
}
else {
vErrors.push(err578);
}
errors++;
}
if(data188 < 1 || isNaN(data188)){
const err579 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/stroke_width/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err579];
}
else {
vErrors.push(err579);
}
errors++;
}
}
else {
const err580 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/stroke_width",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/stroke_width/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err580];
}
else {
vErrors.push(err580);
}
errors++;
}
}
if(data23.timing !== undefined){
let data189 = data23.timing;
if(data189 && typeof data189 == "object" && !Array.isArray(data189)){
if(data189.start === undefined){
const err581 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/required",keyword:"required",params:{missingProperty: "start"},message:"must have required property '"+"start"+"'"};
if(vErrors === null){
vErrors = [err581];
}
else {
vErrors.push(err581);
}
errors++;
}
if(data189.end === undefined){
const err582 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/required",keyword:"required",params:{missingProperty: "end"},message:"must have required property '"+"end"+"'"};
if(vErrors === null){
vErrors = [err582];
}
else {
vErrors.push(err582);
}
errors++;
}
for(const key39 in data189){
if(!((key39 === "start") || (key39 === "end"))){
const err583 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key39},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err583];
}
else {
vErrors.push(err583);
}
errors++;
}
}
if(data189.start !== undefined){
let data190 = data189.start;
if(typeof data190 == "number"){
if(data190 > 1 || isNaN(data190)){
const err584 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/properties/start/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err584];
}
else {
vErrors.push(err584);
}
errors++;
}
if(data190 < 0 || isNaN(data190)){
const err585 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/properties/start/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err585];
}
else {
vErrors.push(err585);
}
errors++;
}
}
else {
const err586 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/start",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/properties/start/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err586];
}
else {
vErrors.push(err586);
}
errors++;
}
}
if(data189.end !== undefined){
let data191 = data189.end;
if(typeof data191 == "number"){
if(data191 > 1 || isNaN(data191)){
const err587 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/properties/end/maximum",keyword:"maximum",params:{comparison: "<=", limit: 1},message:"must be <= 1"};
if(vErrors === null){
vErrors = [err587];
}
else {
vErrors.push(err587);
}
errors++;
}
if(data191 < 0 || isNaN(data191)){
const err588 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/properties/end/minimum",keyword:"minimum",params:{comparison: ">=", limit: 0},message:"must be >= 0"};
if(vErrors === null){
vErrors = [err588];
}
else {
vErrors.push(err588);
}
errors++;
}
}
else {
const err589 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing/end",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/properties/end/type",keyword:"type",params:{type: "number"},message:"must be number"};
if(vErrors === null){
vErrors = [err589];
}
else {
vErrors.push(err589);
}
errors++;
}
}
}
else {
const err590 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/timing",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/timing/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err590];
}
else {
vErrors.push(err590);
}
errors++;
}
}
if(data23.orientation !== undefined){
let data192 = data23.orientation;
if(!((((data192 === "left") || (data192 === "right")) || (data192 === "top")) || (data192 === "bottom"))){
const err591 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3+"/orientation",schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/properties/orientation/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.board_actions.items.oneOf[12].properties.orientation.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err591];
}
else {
vErrors.push(err591);
}
errors++;
}
}
}
else {
const err592 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf/12/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err592];
}
else {
vErrors.push(err592);
}
errors++;
}
var _valid0 = _errs385 === errors;
if(_valid0 && valid12){
valid12 = false;
passing0 = [passing0, 12];
}
else {
if(_valid0){
valid12 = true;
passing0 = 12;
if(props0 !== true){
props0 = true;
}
}
}
}
}
}
}
}
}
}
}
}
}
}
if(!valid12){
const err593 = {instancePath:instancePath+"/steps/" + i2+"/board_actions/" + i3,schemaPath:"#/properties/steps/items/properties/board_actions/items/oneOf",keyword:"oneOf",params:{passingSchemas: passing0},message:"must match exactly one schema in oneOf"};
if(vErrors === null){
vErrors = [err593];
}
else {
vErrors.push(err593);
}
errors++;
}
else {
errors = _errs48;
if(vErrors !== null){
if(_errs48){
vErrors.length = _errs48;
}
else {
vErrors = null;
}
}
}
}
}
else {
const err594 = {instancePath:instancePath+"/steps/" + i2+"/board_actions",schemaPath:"#/properties/steps/items/properties/board_actions/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err594];
}
else {
vErrors.push(err594);
}
errors++;
}
}
if(data18.gesture !== undefined){
let data193 = data18.gesture;
if(data193 && typeof data193 == "object" && !Array.isArray(data193)){
if(data193.kind === undefined){
const err595 = {instancePath:instancePath+"/steps/" + i2+"/gesture",schemaPath:"#/properties/steps/items/properties/gesture/required",keyword:"required",params:{missingProperty: "kind"},message:"must have required property '"+"kind"+"'"};
if(vErrors === null){
vErrors = [err595];
}
else {
vErrors.push(err595);
}
errors++;
}
if(data193.target_element_id === undefined){
const err596 = {instancePath:instancePath+"/steps/" + i2+"/gesture",schemaPath:"#/properties/steps/items/properties/gesture/required",keyword:"required",params:{missingProperty: "target_element_id"},message:"must have required property '"+"target_element_id"+"'"};
if(vErrors === null){
vErrors = [err596];
}
else {
vErrors.push(err596);
}
errors++;
}
for(const key40 in data193){
if(!((key40 === "kind") || (key40 === "target_element_id"))){
const err597 = {instancePath:instancePath+"/steps/" + i2+"/gesture",schemaPath:"#/properties/steps/items/properties/gesture/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key40},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err597];
}
else {
vErrors.push(err597);
}
errors++;
}
}
if(data193.kind !== undefined){
let data194 = data193.kind;
if(!(((((data194 === "idle") || (data194 === "look_board")) || (data194 === "point")) || (data194 === "write")) || (data194 === "explain"))){
const err598 = {instancePath:instancePath+"/steps/" + i2+"/gesture/kind",schemaPath:"#/properties/steps/items/properties/gesture/properties/kind/enum",keyword:"enum",params:{allowedValues: schema31.properties.steps.items.properties.gesture.properties.kind.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err598];
}
else {
vErrors.push(err598);
}
errors++;
}
}
if(data193.target_element_id !== undefined){
let data195 = data193.target_element_id;
if((typeof data195 !== "string") && (data195 !== null)){
const err599 = {instancePath:instancePath+"/steps/" + i2+"/gesture/target_element_id",schemaPath:"#/properties/steps/items/properties/gesture/properties/target_element_id/type",keyword:"type",params:{type: schema31.properties.steps.items.properties.gesture.properties.target_element_id.type},message:"must be string,null"};
if(vErrors === null){
vErrors = [err599];
}
else {
vErrors.push(err599);
}
errors++;
}
}
}
else {
const err600 = {instancePath:instancePath+"/steps/" + i2+"/gesture",schemaPath:"#/properties/steps/items/properties/gesture/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err600];
}
else {
vErrors.push(err600);
}
errors++;
}
}
}
else {
const err601 = {instancePath:instancePath+"/steps/" + i2,schemaPath:"#/properties/steps/items/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err601];
}
else {
vErrors.push(err601);
}
errors++;
}
}
}
else {
const err602 = {instancePath:instancePath+"/steps",schemaPath:"#/properties/steps/type",keyword:"type",params:{type: "array"},message:"must be array"};
if(vErrors === null){
vErrors = [err602];
}
else {
vErrors.push(err602);
}
errors++;
}
}
if(data.final_summary !== undefined){
let data196 = data.final_summary;
if(typeof data196 === "string"){
if(func2(data196) < 1){
const err603 = {instancePath:instancePath+"/final_summary",schemaPath:"#/properties/final_summary/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err603];
}
else {
vErrors.push(err603);
}
errors++;
}
}
else {
const err604 = {instancePath:instancePath+"/final_summary",schemaPath:"#/properties/final_summary/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err604];
}
else {
vErrors.push(err604);
}
errors++;
}
}
if(data.problem_revision !== undefined){
let data197 = data.problem_revision;
if(!((typeof data197 == "number") && (!(data197 % 1) && !isNaN(data197)))){
const err605 = {instancePath:instancePath+"/problem_revision",schemaPath:"#/properties/problem_revision/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err605];
}
else {
vErrors.push(err605);
}
errors++;
}
if(typeof data197 == "number"){
if(data197 < 1 || isNaN(data197)){
const err606 = {instancePath:instancePath+"/problem_revision",schemaPath:"#/properties/problem_revision/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err606];
}
else {
vErrors.push(err606);
}
errors++;
}
}
}
if(data.source_message_id !== undefined){
let data198 = data.source_message_id;
if(typeof data198 === "string"){
if(func2(data198) > 200){
const err607 = {instancePath:instancePath+"/source_message_id",schemaPath:"#/properties/source_message_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err607];
}
else {
vErrors.push(err607);
}
errors++;
}
if(func2(data198) < 1){
const err608 = {instancePath:instancePath+"/source_message_id",schemaPath:"#/properties/source_message_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err608];
}
else {
vErrors.push(err608);
}
errors++;
}
}
else {
const err609 = {instancePath:instancePath+"/source_message_id",schemaPath:"#/properties/source_message_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err609];
}
else {
vErrors.push(err609);
}
errors++;
}
}
if(data.source_photo_id !== undefined){
let data199 = data.source_photo_id;
if(typeof data199 === "string"){
if(func2(data199) > 200){
const err610 = {instancePath:instancePath+"/source_photo_id",schemaPath:"#/properties/source_photo_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err610];
}
else {
vErrors.push(err610);
}
errors++;
}
if(func2(data199) < 1){
const err611 = {instancePath:instancePath+"/source_photo_id",schemaPath:"#/properties/source_photo_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err611];
}
else {
vErrors.push(err611);
}
errors++;
}
}
else {
const err612 = {instancePath:instancePath+"/source_photo_id",schemaPath:"#/properties/source_photo_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err612];
}
else {
vErrors.push(err612);
}
errors++;
}
}
if(data.evidence_ref !== undefined){
let data200 = data.evidence_ref;
if(data200 && typeof data200 == "object" && !Array.isArray(data200)){
if(data200.message_id === undefined){
const err613 = {instancePath:instancePath+"/evidence_ref",schemaPath:"#/properties/evidence_ref/required",keyword:"required",params:{missingProperty: "message_id"},message:"must have required property '"+"message_id"+"'"};
if(vErrors === null){
vErrors = [err613];
}
else {
vErrors.push(err613);
}
errors++;
}
if(data200.problem_revision === undefined){
const err614 = {instancePath:instancePath+"/evidence_ref",schemaPath:"#/properties/evidence_ref/required",keyword:"required",params:{missingProperty: "problem_revision"},message:"must have required property '"+"problem_revision"+"'"};
if(vErrors === null){
vErrors = [err614];
}
else {
vErrors.push(err614);
}
errors++;
}
if(data200.mode === undefined){
const err615 = {instancePath:instancePath+"/evidence_ref",schemaPath:"#/properties/evidence_ref/required",keyword:"required",params:{missingProperty: "mode"},message:"must have required property '"+"mode"+"'"};
if(vErrors === null){
vErrors = [err615];
}
else {
vErrors.push(err615);
}
errors++;
}
for(const key41 in data200){
if(!(((key41 === "message_id") || (key41 === "problem_revision")) || (key41 === "mode"))){
const err616 = {instancePath:instancePath+"/evidence_ref",schemaPath:"#/properties/evidence_ref/additionalProperties",keyword:"additionalProperties",params:{additionalProperty: key41},message:"must NOT have additional properties"};
if(vErrors === null){
vErrors = [err616];
}
else {
vErrors.push(err616);
}
errors++;
}
}
if(data200.message_id !== undefined){
let data201 = data200.message_id;
if(typeof data201 === "string"){
if(func2(data201) > 200){
const err617 = {instancePath:instancePath+"/evidence_ref/message_id",schemaPath:"#/properties/evidence_ref/properties/message_id/maxLength",keyword:"maxLength",params:{limit: 200},message:"must NOT have more than 200 characters"};
if(vErrors === null){
vErrors = [err617];
}
else {
vErrors.push(err617);
}
errors++;
}
if(func2(data201) < 1){
const err618 = {instancePath:instancePath+"/evidence_ref/message_id",schemaPath:"#/properties/evidence_ref/properties/message_id/minLength",keyword:"minLength",params:{limit: 1},message:"must NOT have fewer than 1 characters"};
if(vErrors === null){
vErrors = [err618];
}
else {
vErrors.push(err618);
}
errors++;
}
}
else {
const err619 = {instancePath:instancePath+"/evidence_ref/message_id",schemaPath:"#/properties/evidence_ref/properties/message_id/type",keyword:"type",params:{type: "string"},message:"must be string"};
if(vErrors === null){
vErrors = [err619];
}
else {
vErrors.push(err619);
}
errors++;
}
}
if(data200.problem_revision !== undefined){
let data202 = data200.problem_revision;
if(!((typeof data202 == "number") && (!(data202 % 1) && !isNaN(data202)))){
const err620 = {instancePath:instancePath+"/evidence_ref/problem_revision",schemaPath:"#/properties/evidence_ref/properties/problem_revision/type",keyword:"type",params:{type: "integer"},message:"must be integer"};
if(vErrors === null){
vErrors = [err620];
}
else {
vErrors.push(err620);
}
errors++;
}
if(typeof data202 == "number"){
if(data202 < 1 || isNaN(data202)){
const err621 = {instancePath:instancePath+"/evidence_ref/problem_revision",schemaPath:"#/properties/evidence_ref/properties/problem_revision/minimum",keyword:"minimum",params:{comparison: ">=", limit: 1},message:"must be >= 1"};
if(vErrors === null){
vErrors = [err621];
}
else {
vErrors.push(err621);
}
errors++;
}
}
}
if(data200.mode !== undefined){
let data203 = data200.mode;
if(!(((data203 === "original") || (data203 === "hypothesis")) || (data203 === "concept_example"))){
const err622 = {instancePath:instancePath+"/evidence_ref/mode",schemaPath:"#/properties/evidence_ref/properties/mode/enum",keyword:"enum",params:{allowedValues: schema31.properties.evidence_ref.properties.mode.enum},message:"must be equal to one of the allowed values"};
if(vErrors === null){
vErrors = [err622];
}
else {
vErrors.push(err622);
}
errors++;
}
}
}
else {
const err623 = {instancePath:instancePath+"/evidence_ref",schemaPath:"#/properties/evidence_ref/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err623];
}
else {
vErrors.push(err623);
}
errors++;
}
}
}
else {
const err624 = {instancePath,schemaPath:"#/type",keyword:"type",params:{type: "object"},message:"must be object"};
if(vErrors === null){
vErrors = [err624];
}
else {
vErrors.push(err624);
}
errors++;
}
validate20.errors = vErrors;
return errors === 0;
}
validate20.evaluated = {"props":true,"dynamicProps":false,"dynamicItems":false};
