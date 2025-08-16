function updateStatus(response, status, xhr) {
  var sp = document.getElementById('station_id');
  if( sp != null ) {
    sp.innerHTML = response['station_id'];
    sp.classList.remove("loading");
  }
  
  sp = document.getElementById('capture_active');
  if( sp != null ) {
    if( response['capture']['running'] ) {
      sp.innerHTML = 'active'
    } else {
      sp.innerHTML = 'waiting for next start at ' + response['capture']['next_start'];
    }
    sp.classList.remove("loading");
  }
}

function updateLinks(response, status, xhr) {
  sta = response['station_id'];
  cc = sta.slice(0, 2);
  
  var last_week = new Date();
  last_week.setTime(last_week.getDate() - 7);
  var lw_str = last_week.getFullYear() + "-" + (last_week.getMonth() + 1) + "-" + last_week.getDay();
  
  var ln = document.getElementById('weblog');
  if( ln != null ) {
    ln.innerHTML = 'Weblog Entry';
    ln.href = "https://globalmeteornetwork.org/weblog/" + cc + "/" + sta + "/latest/";
    ln.classList.remove("loading");
  }
  
  ln = document.getElementById('recent_contrib');
  if( ln != null ) {
    ln.innerHTML = 'Recent Contributions';
    ln.href = "https://explore.globalmeteornetwork.org/gmn_data_store/participating_station?created_at__gte=" + lw_str + "&station_code__exact=" + sta + "&_sort_desc=created_at";
    ln.classList.remove("loading");
  }
  
  ln = document.getElementById('recent_enable');
  if( ln != null ) {
    ln.innerHTML = "Recently Enabled (" + response['station_id'] + " + One Other Station)";
    ln.href = "https://explore.globalmeteornetwork.org/gmn_data_store/-/query?sql=SELECT+ps_summary.meteor_unique_trajectory_identifier%2C%0D%0A+++++++REPLACE%28REPLACE%28ps_summary.stations%2C+%3Ap0%2C+%27%27%29%2C+%27%2C%27%2C+%27%27%29+as+other_station%2C%0D%0A+++++++m.beginning_utc_time%2C%0D%0A+++++++m.elev_deg%2C%0D%0A+++++++m.latbeg_n_deg%2C%0D%0A+++++++m.lonbeg_e_deg%2C%0D%0A+++++++m.latend_n_deg%2C%0D%0A+++++++m.lonend_e_deg%2C%0D%0A+++++++m.htbeg_km%2C%0D%0A+++++++m.htend_km%2C%0D%0A+++++++m.duration_sec%2C%0D%0A+++++++m.peak_absmag%2C%0D%0A+++++++m.vgeo_km_s%2C%0D%0A+++++++m.created_at+as+meteor_created_at%2C%0D%0A+++++++m.updated_at+as+meteor_updated_at%0D%0AFROM+%28%0D%0A++++SELECT+meteor_unique_trajectory_identifier%2C+%0D%0A+++++++++++GROUP_CONCAT%28station_code%29+as+stations%2C%0D%0A+++++++++++COUNT%28*%29+as+station_count%2C%0D%0A+++++++++++MAX%28created_at%29+as+latest_created_at%0D%0A++++FROM+participating_station+%0D%0A++++WHERE+meteor_unique_trajectory_identifier+IN+%28%0D%0A++++++++SELECT+meteor_unique_trajectory_identifier+%0D%0A++++++++FROM+participating_station+%0D%0A++++++++WHERE+station_code+%3D+%3Ap0%0D%0A++++%29%0D%0A++++GROUP+BY+meteor_unique_trajectory_identifier%0D%0A++++HAVING+COUNT%28DISTINCT+station_code%29+%3D+2%0D%0A%29+ps_summary%0D%0AJOIN+meteor+m+ON+ps_summary.meteor_unique_trajectory_identifier+%3D+m.unique_trajectory_identifier%0D%0AORDER+BY+ps_summary.latest_created_at+DESC%0D%0ALIMIT+101%3B&p0=" + sta + "&p1=" + lw_str;
    ln.classList.remove("loading");
  }
}

function fetchLatest() {
  $.ajax({'url': '/latest',
          'success': function(response, status, xhr) {
            updateStatus(response, status, xhr);
            updateLinks(response, status, xhr);
            setTimeout(fetchLatest, 30000);
          },
          'error': function() {
            setTimeout(fetchLatest, 30000);
          }
         });
}

function initializePage() {
  fetchLatest();
}
