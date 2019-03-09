{% set count = 0 %}
            {% for s in scraper_list %}
            {% if s.status ==  1|string and s.meta != 0|string%}
            {% set count = count +1 %}
            {% endif %}
            {% endfor %}

            {% if count == 0 %}

            {% for s in scraper_list %}
            {% if s.status ==  1|string and s.meta != 0|string%}
            <tr>
              <td>{{ s.provider }}</td>
              <td>{{ s.city }}</td>
              <td>{{ s.keyword }}</td>
              {% if s.status == 1|string and s.meta == 0|string %}
              <td>Running</td>
              <td><a class=" button is-small rubik is-info" href="{{url_for('task_pause' , task_id = s.id )}}">Pause</a> </td>
              {% elif s.status ==  0|string %}
              <td>Stopped</td>
              <td><a class=" button is-small rubik is-primary"
                  href="{{url_for('push_scraper_to_queue' , task_id = s.id )}}">Run</a> </td>
              {% elif s.status ==  2|string %}
              <td>Finished</td>
              <td><a class=" button is-small rubik is-success has-text-weight-bold is-static"><span
                    class="icon icon-btn-in"><i data-feather="check-circle"></i></span>Done</a> </td>
              <td><a class=" button is-small has-text-weight-bold rubik is-warning" id="src-results-{{loop.index}}"><span
                    class="icon icon-btn-in"><i data-feather="activity"></i></span> Results</a> </td>
      
              <div class="modal" id="modal-src-{{loop.index}}">
                <div class="modal-background"></div>
                <div class="modal-content">
                  <div class="box has-text-centered" style="margin-bottom : 0px;">
                    <p class=" is-size-4 has-text-weight-bold ">Scrape Results for {{s.city}} </p>
                    <p class=" subtitle has-text-grey rubik">via {{s.provider}} </p>
      
                    <button class=" button rubik is-fullwidth is-black"><span class="icon icon-btn-in"><i
                          data-feather="book-open"></i></span> View Full Report</button>
                    <br>
                    <br>
                    <div class="columns">
                      <div class="column ">
                        <div class="notification is-success has-text-centered">
                          <p class=" is-size-5 has-text-weight-bold">
                            <span class="icon icon-btn"><i data-feather="user-check"></i></span>
                            Successfully Scraped
                          </p>
                          <hr>
      
                          <p>
                            <span class="is-size-1 has-text-weight-bold" id="success_sent_{{loop.index}}"></span>
                            <br>
                            <span class="subtitle">Contacts</span>
                            <br>
      
                          </p>
      
                        </div>
                      </div>
      
                    </div>
                  </div>
                </div>
                <button class="modal-close is-large" aria-label="close"></button>
              </div>
              <script>
                $(document).ready(function () {
                  axios.post("{{url_for('src_results' , job_id = s.id , keyword = s.keyword)}}",
                  )
                    .then(function (response) {
                      console.log(response.data);
                      $("#success_sent_{{loop.index}}").html(response.data.con_all);
                    })
                    .catch(function (error) {
                      console.log(response.data.mssg);
                    });
                });
      
      
                document.querySelector('#src-results-{{loop.index}}').addEventListener('click', function (event) {
                  event.preventDefault();
                  var modal = document.querySelector('#modal-src-{{loop.index}}');  // assuming you have only 1
                  var html = document.querySelector('html');
                  modal.classList.add('is-active');
                  html.classList.add('is-clipped');
      
                  document.querySelector('.modal-close').addEventListener('click', function (e) {
                    e.preventDefault();
                    modal.classList.remove('is-active');
                    html.classList.remove('is-clipped');
                  });
      
                  modal.querySelector('.modal-background').addEventListener('click', function (e) {
                    e.preventDefault();
                    modal.classList.remove('is-active');
                    html.classList.remove('is-clipped');
      
      
                  });
      
                });
              </script>
              {% elif s.status ==  1|string and s.meta != 0|string %}
              <td>Paused</td>
              <td><a class=" button is-small rubik is-primary"
                  href="{{url_for('push_scraper_to_queue' , task_id = s.id )}}">Resume</a> </td>
              {% endif %}
            </tr>
            {% endif %}
            {% endfor %}
            {% else %}
            <div class="notification is-light">
              <p>There are no items here. Check other tabs for more scraper tasks or create a new one.</p>
            </div>
            {% endif %}