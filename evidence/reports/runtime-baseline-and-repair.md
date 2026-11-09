# 적용 및 CPU 검증 결과

4개 운영 소스 수정 완료. `before-apply-receipt.json`은 적용 전 운영 해시가 보관 base와 같음을 증명한다. 최종 해시는 `after-apply-receipt.json`이다. 정책·운영 장부·서버 프로세스·모델은 변경하지 않았다.

실제 학생 resident text 요청에서 scope/학생 cap/횟수/시간 허용 조건 확인 후, 전체 저장 검사 전에 부모와 자식의 유휴 시각을 한 번 갱신한다. 예약 기록 이전이므로 저장 검사 실패시 예약은 생기지 않는다. max600은 유지하며 GET/Heami/예산 거부/이미 만료/다른 expected instance는 갱신하지 않는다. 세부 경계와 ACK 송신 한계는 `DESIGN_KO.md`를 따른다.

검증:

- 신규 순수 CPU 26개 통과(`unit-01.xml`). exact owner/key/직전 요청, expected instance 불일치, 취소·deadline, ACK 위조/늦은 ACK, 중복 job, max timer 불변, GET 무갱신, 예산 거부·저장 실패·Heami 제외를 확인했다.
- 실제 Windows 프로세스의 **모의 객체** 및 기존 resident/예산/Heami CPU 회귀 총71개 통과(`native-01.xml`). 신규 프로세스 검사는 idle3초 fixture에서 1.4초 뒤 ACK 갱신 후 다시 2초 지나 같은 PID·같은 모의 객체·load0을 확인했다. 실제 모델 합성 또는 성능 증거가 아니다.
- 관련 dispatch/취소 소유권 회귀에서 기존 reserve 모의 함수가 새 선택 인수를 받지 못한 테스트 1건 실패를 보존했다(`dispatch-01.xml`). 제품 결함이 아니며 해당 테스트 signature만 보완했다.
- 지연된 타이머 callback 상태에서 run 진입의 idle/max 재확인 2개를 추가하고, 관련 회귀58개 통과(`dispatch-02.xml`, 신규 모의 프로세스 1개는 이미 통과하여 반복 제외). 중복 제거한 서로 다른 테스트는 **103개 통과**다.

자식 stdout과 watchdog state lock 분리는 소스 및 독립 코드 검토로 확인했다. 의도적으로 stdout을 무한 봉쇄하는 실제 프로세스 실험이나 600초 대기 실험은 하지 않았다. 최대 수명 변경 금지와 만료 경합은 단축/모의 CPU 경계로 확인한 범위다.

이번 결과는 느린 저장 검사·모델 import·load·generation의 비용이 줄었다는 뜻이 아니다. 실제 학생 경로의 동일 인스턴스 유지와 지연은 부모 담당 실제 실행으로 별도 측정해야 한다. NOT_READY/H_PENDING 해제 근거가 아니다.
