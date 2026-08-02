# ai-builder-portfolio

This document describes how the models are being evaluated for this project:

**Requirement for the project: **
- Extract the details such as Exam name, academic eligibility, Domicile eligibility from a text currently.  
- Able to do web browsing
- Provide structured output  
- Be economical to Scale

Based on the above criteria, it is established that frontier level reason is not required.


Data Volume:
- Number of exam records is around 100 exams, 
- the model will check for the updates twice a week to have a balance between freshness and cost
- The query will be batched to 5 exams per API call to not overload the LLM

Test Case for LLM extraction:
MHT-CET : Extract the following exam listing into JSON with fields: exam_name, eligibility_level, state, stream, application_deadline. If a field isn't mentioned, use null.
Text: 'The Maharashtra State CET for Engineering (MHT-CET) is open to students who have completed Class 12 with PCM. Applications close on 15 March. Open to all states but seats are reserved for Maharashtra domicile students. 
AP POLYCET (Andhra Pradesh Polytechnic). Min Qualification: Class 10 Pass. Stream Requirement: Any. State: Andhra Pradesh. Additional Requirements: State domicile required;

**Among the API model provider, I considered**:
Claude Haiku 4.5
- Able to provide correct extraction
- Tokken economics: With a input cost of Input $1 / MTok and output cost of $5 / MTok the average cost will be $0.64-1.28/month

Gemini 3.6 Flash
- Able to provide correct extraction
- Tokken economics: Free for prototyping,

Hence will use Gemini 3.6 Flash for API calls. If scaling constraints come, will shift to a paid version.

Local LLMs
On a beginner gaming PC two models were tested:

Qwen 2.5:7B
- A bigger model
- Able to extract content correctly
- Slightly slower because of the size

Gemma2:2B
- A smaller model
- Able to extract content correctly
- Slightly faster when compare to Qwen 2.5:7B


**Project Architecture: Split LLM Architecture**
- API for web search and local for extraction and structuring output


**Key finding: **
Initial testing used a field named state, which every model (Qwen 2.5:7B, Gemma2:2B, Claude Haiku 4.5, Gemini 3.6 Flash) misread as "the applicant's home state," collapsing MHT-CET to state: Maharashtra despite the exam being open nationally with only reserved seats for Maharashtra domicile. Renaming the field to explicitly ask for state-level eligibility vs. all-India applicability resolved this across all models, including the smallest local model tested (Gemma2:2B). Conclusion: the failure was a schema design issue, not a model capability limitation — worth remembering as this project scales to real exam data with similarly ambiguous eligibility language.

**Rationale: **
- No visible difference in content extraction among the Local LLM vs API based models on the sample test cases
- Split LLM Architecture will help the cost aspect as well if we moved to paid API models 

**What would I revisit:**
API LLM Model: If the Model becomes unavailable, or not performing well on the larger data
API batch size, if batch size needs to be decreased for quality enhancements
Twice a week run for updates: In case the project website is used by larger audience
Split LLM Architecture: In case the project website is used by larger audience
